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
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_record = str(mx_records[0].exchange)

            server = smtplib.SMTP(timeout=30)  # Increased timeout
            server.set_debuglevel(1)  # Enable debug logging

            # Get IP from pool
            current_ip = self.ip_pool.get_next_ip()
            server.source_address = (current_ip, 0)

            # Connect and verify
            server.connect(mx_record)
            server.ehlo_or_helo_if_needed()

            # Some servers require MAIL FROM
            sender_domain = domain  # Use recipient's domain
            server.mail(f'verify@{sender_domain}')
            code, message = server.rcpt(email)

            # Consider both 250 and 251 as valid responses
            return code in [250, 251]

        except smtplib.SMTPServerDisconnected:
            self.logger.warning(f"Server disconnected for {email}")
            return True  # Consider it valid if server disconnects
        except Exception as e:
            self.logger.error(f"SMTP Error for {email}: {str(e)}")
            return True  # Default to valid on errors
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

    def validate_email(self, email: str) -> str:
        with self.lock:
            if email in self.cache:
                return self.cache[email]

        try:
            # Step 1: Basic Validation
            if not self.is_valid_syntax(email):
                result = EmailValidationResult.INVALID_SYNTAX
                return result

            domain = email.split('@')[1]

            # Step 2: Domain and MX Record Check
            if not self.has_valid_mx_records(domain):
                result = EmailValidationResult.INVALID_DOMAIN
                return result

            # Step 3: SMTP Handshake
            if not self.smtp_handshake(email):
                result = EmailValidationResult.SMTP_FAILED
                return result

            # Step 4: Additional Checks for Valid Emails
            if self.is_disposable_email(domain):
                result = EmailValidationResult.DISPOSABLE_EMAIL
            elif self.is_role_based(email):
                result = EmailValidationResult.ROLE_BASED
            elif self.is_free_email(domain):
                result = EmailValidationResult.FREE_EMAIL
            else:
                result = EmailValidationResult.VALID

        except Exception as e:
            self.logger.error(f"Validation error for {email}: {str(e)}")
            result = str(e)

        with self.lock:
            self.cache[email] = result
        return result