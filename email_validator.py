import re
import dns.resolver
import smtplib
import socket
from datetime import datetime
from threading import Lock
import time
import logging
from typing import Dict, Set
from ip_pool import IPPool


class EmailValidationResult:
    VALID = 'Valid'
    INVALID_SYNTAX = 'Invalid Syntax'
    INVALID_LENGTH = 'Invalid Length'
    INVALID_DOMAIN = 'Invalid Domain'
    DISPOSABLE_EMAIL = 'Disposable Email'
    ROLE_BASED = 'Role-based Email'
    FREE_EMAIL = 'Free Email Provider'
    CUSTOM_DOMAIN = 'Custom Domain Email'
    TYPO_DOMAIN = 'Possible Typo in Domain'
    TIMEOUT = 'Verification Timeout'
    BLOCKED = 'IP Blocked by Server'
    SMTP_FAILED = 'SMTP Verification Failed'


class EmailValidator:
    def __init__(self, ips=None):
        self.ip_pool = IPPool(ips)  # Initialize IP pool
        self.cache = {}
        self.lock = Lock()
        self.email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

        # Initialize validation lists
        self.disposable_domains: Set[str] = {
            'tempmail.com', 'guerrillamail.com', 'throwawaymail.com',
            'mailinator.com', '10minutemail.com', 'yopmail.com',
            'tempmail.net', 'disposablemail.com', 'sharklasers.com',
            'mintemail.com', 'mailnull.com', 'emailondeck.com'
        }

        self.free_email_domains: Set[str] = {
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'aol.com', 'mail.com', 'protonmail.com', 'icloud.com',
            'zoho.com', 'yandex.com'
        }

        self.role_based_accounts: Set[str] = {
            'admin', 'support', 'info', 'sales', 'contact',
            'help', 'billing', 'marketing', 'webmaster', 'postmaster',
            'hostmaster', 'abuse', 'noc', 'security', 'no-reply',
            'noreply', 'hr', 'jobs', 'careers', 'customercare',
            'enquiry', 'feedback'
        }

        # Common typos in domain names
        self.common_domains = {
            'gmail.com': ['gmal.com', 'gmial.com', 'gmai.com', 'gmil.com', 'gamil.com'],
            'yahoo.com': ['yaho.com', 'yahooo.com', 'yaho.com', 'ymail.com'],
            'hotmail.com': ['hotmal.com', 'hotmial.com', 'hotmall.com', 'hotamail.com']
        }

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return '127.0.0.1'

    def is_valid_syntax(self, email: str) -> bool:
        return bool(re.match(self.email_regex, email))

    def has_valid_length(self, email: str) -> bool:
        """Check if email meets length requirements per RFC 5321."""
        if len(email) > 254:
            return False
        local_part = email.split('@')[0]
        return len(local_part) <= 64

    def has_valid_domain_parts(self, domain: str) -> bool:
        """Validate domain parts according to RFC 1035."""
        try:
            parts = domain.split('.')
            return all(1 <= len(part) <= 63 for part in parts)
        except Exception:
            return False

    def is_disposable_email(self, domain: str) -> bool:
        """Check if email uses a disposable domain."""
        return domain.lower() in self.disposable_domains

    def is_role_based(self, email: str) -> bool:
        """Check if email is a role-based account."""
        local_part = email.split('@')[0].lower()
        return local_part in self.role_based_accounts

    def is_free_email(self, domain: str) -> bool:
        """Check if email uses a free email provider."""
        return domain.lower() in self.free_email_domains

    def check_for_typos(self, domain: str) -> tuple[bool, str]:
        """Check for common typos in domain names."""
        domain = domain.lower()
        for correct_domain, typos in self.common_domains.items():
            if domain in typos:
                return True, correct_domain
        return False, ''

    def has_valid_mx_records(self, domain: str) -> bool:
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            return len(mx_records) > 0
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout):
            return False
        except Exception as e:
            self.logger.error(f"MX record check error for {domain}: {str(e)}")
            return False

    def smtp_handshake(self, email: str) -> bool:
        domain = email.split('@')[1]
        server = None

        try:
            # Get IP from pool
            current_ip = self.ip_pool.get_next_ip()

            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_record = str(mx_records[0].exchange)

            server = smtplib.SMTP(timeout=10)
            server.set_debuglevel(0)

            # Use IP from pool
            server.source_address = (current_ip, 0)

            server.connect(mx_record)
            server.ehlo_or_helo_if_needed()

            server.mail("")
            code, message = server.rcpt(email)
            server.quit()
            return code == 250

        except Exception as e:
            self.logger.error(f"SMTP Error for {email}: {str(e)}")
            return False
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

    def validate_email(self, email: str) -> str:
        """
        Comprehensive email validation with multiple checks.
        Returns a string indicating the validation result.
        """
        with self.lock:
            if email in self.cache:
                return self.cache[email]

        try:
            # Basic checks
            if not self.is_valid_syntax(email):
                result = EmailValidationResult.INVALID_SYNTAX
            elif not self.has_valid_length(email):
                result = EmailValidationResult.INVALID_LENGTH
            else:
                # Domain specific checks
                domain = email.split('@')[1]

                if not self.has_valid_domain_parts(domain):
                    result = EmailValidationResult.INVALID_DOMAIN
                elif not self.has_valid_mx_records(domain):
                    result = EmailValidationResult.INVALID_DOMAIN
                elif self.is_disposable_email(domain):
                    result = EmailValidationResult.DISPOSABLE_EMAIL
                elif self.is_role_based(email):
                    result = EmailValidationResult.ROLE_BASED
                else:
                    # Check for typos
                    has_typo, correct_domain = self.check_for_typos(domain)
                    if has_typo:
                        result = f"{EmailValidationResult.TYPO_DOMAIN} (Did you mean {correct_domain}?)"
                    # Provider type check
                    elif self.is_free_email(domain):
                        if not self.smtp_handshake(email):
                            result = EmailValidationResult.SMTP_FAILED
                        else:
                            result = EmailValidationResult.FREE_EMAIL
                    else:
                        if not self.smtp_handshake(email):
                            result = EmailValidationResult.SMTP_FAILED
                        else:
                            result = EmailValidationResult.CUSTOM_DOMAIN

        except Exception as e:
            self.logger.error(f"Validation error for {email}: {str(e)}")
            result = str(e)

        with self.lock:
            self.cache[email] = result
        return result
