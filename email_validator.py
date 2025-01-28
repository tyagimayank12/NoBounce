import re
import dns.resolver
import smtplib
import socket
from datetime import datetime
from threading import Lock
import logging
from typing import Dict, Set
import requests
import socks
from functools import lru_cache
from ip_pool import IPPool

# RateLimiter implementation
class RateLimiter:
    def __init__(self, max_calls, period):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = Lock()

    def limited(func):
        def wrapper(self, *args, **kwargs):
            with self.lock:
                now = datetime.now()
                self.calls = [call for call in self.calls if (now - call).total_seconds() < self.period]
                if len(self.calls) >= self.max_calls:
                    return False
                self.calls.append(now)
            return func(self, *args, **kwargs)
        return wrapper

class EmailValidationResult:
    VALID = 'Valid'
    INVALID_SYNTAX = 'Invalid Syntax'
    INVALID_LENGTH = 'Invalid Length'
    INVALID_DOMAIN = 'Invalid Domain'
    DISPOSABLE_EMAIL = 'Disposable Email'
    ROLE_BASED = 'Role-based Email'
    FREE_EMAIL = 'Free Email Provider'
    CUSTOM_DOMAIN = 'Custom Domain Email'
    SMTP_FAILED = 'SMTP Verification Failed'


class EmailValidator:
    def __init__(self, ips=None):
        self.ip_pool = IPPool()
        self.cache = {}
        self.lock = Lock()
        self.email_regex = re.compile(r'''
            ^(?!\.)                            
            (?!.*\.@)                          
            (?!.*\.\.)                         
            [a-zA-Z0-9_+&*-]+                  
            (?:\.[a-zA-Z0-9_+&*-]+)*           
            @
            (?:[a-zA-Z0-9-]+\.)+               
            [a-zA-Z]{2,63}                     
            (?<!\.)$                           
        ''', re.VERBOSE)

        self.disposable_domains = {
            'tempmail.com', 'guerrillamail.com', 'throwawaymail.com',
            'mailinator.com', '10minutemail.com', 'yopmail.com'
        }

        self.free_email_domains = {
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'aol.com', 'mail.com', 'protonmail.com'
        }

        self.role_based_accounts = {
            'admin', 'support', 'contact', 'help', 'billing',
            'marketing', 'webmaster', 'postmaster', 'hostmaster',
            'abuse', 'noc', 'security', 'no-reply', 'noreply'
        }

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def smtp_handshake(self, email: str) -> bool:
        domain = email.split('@')[1]
        server = None

        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_records = sorted(mx_records, key=lambda x: x.preference)

            for mx in mx_records:
                mx_host = str(mx.exchange).rstrip('.')
                try:
                    connection = self.ip_pool.get_connection()
                    proxies = {
                        'http': connection['config']['url'],
                        'https': connection['config']['url']
                    }

                    session = requests.Session()
                    session.proxies = proxies
                    server = smtplib.SMTP(timeout=30)

                    server.set_debuglevel(1)
                    server.connect(mx_host)
                    server.ehlo()

                    # Try different sender addresses
                    sender_addresses = [
                        f'noreply@{domain}',
                        'verify@verify.com',
                        ''
                    ]

                    for sender in sender_addresses:
                        try:
                            server.mail(sender)
                            code, message = server.rcpt(email)

                            self.logger.info(f"SMTP response for {email}: Code={code}, Message={message}")

                            if code == 250:
                                return True
                            if code in [421, 450, 451]:
                                continue
                            if code in [550, 551, 553, 554]:
                                return False

                        except smtplib.SMTPException as e:
                            self.logger.debug(f"SMTP error with sender {sender}: {str(e)}")
                            continue

                except Exception as e:
                    self.logger.error(f"Connection error for {email}: {str(e)}")
                    continue
                finally:
                    if server:
                        try:
                            server.quit()
                        except:
                            pass

            return False

        except Exception as e:
            self.logger.error(f"DNS error for {email}: {str(e)}")
            return False

    def validate_email(self, email: str) -> dict:
        """Return detailed validation results"""
        result = {
            'email': email,
            'valid': False,
            'details': [],
            'smtp_debug': []
        }

        try:
            # Check syntax
            if not self.is_valid_syntax(email):
                result['details'].append("Failed syntax check")
                return result

            domain = email.split('@')[1]

            # Check MX records
            if not self.has_valid_mx_records(domain):
                result['details'].append("Failed MX records check")
                return result

            # Check disposable
            if self.is_disposable_email(domain):
                result['details'].append("Disposable email")
                return result

            # SMTP check
            if self.smtp_handshake(email):
                result['valid'] = True
            else:
                result['details'].append("Failed SMTP check")

        except Exception as e:
            result['details'].append(f"Error: {str(e)}")

        return result

    def is_valid_syntax(self, email: str) -> bool:
        return bool(re.match(self.email_regex, email))

    def has_valid_mx_records(self, domain: str) -> bool:
        try:
            # Check both MX and A/AAAA records as fallback
            try:
                dns.resolver.resolve(domain, 'MX', lifetime=5)
                return True
            except dns.resolver.NoAnswer:
                # Fallback to A record check
                dns.resolver.resolve(domain, 'A', lifetime=5)
                return True
        except dns.resolver.NXDOMAIN:
            return False
        except Exception as e:
            self.logger.warning(f"DNS error for {domain}: {str(e)}")
            return False

    def validate_batch(self, emails: list, workers=8):
        """Parallel validation using ThreadPool"""
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.validate_email, emails))

    def is_disposable_email(self, domain: str) -> bool:
        return domain.lower() in self.disposable_domains

    def is_role_based(self, email: str) -> bool:
        local_part = email.split('@')[0].lower()
        return local_part in self.role_based_accounts

    def is_free_email(self, domain: str) -> bool:
        return domain.lower() in self.free_email_domains

    def get_status(self):
        """Get IP pool status"""
        return self.ip_pool.get_status()


class SMTPConnection:
    def __init__(self, connection):
        self.connection = connection
        self.server = None

    def __enter__(self):
        if self.connection['type'] == 'proxy':
            self.server = smtplib.SMTP(
                timeout=20,
                source_address=(self.connection['ip'], 0)
            )
        else:
            # Handle SOCKS proxies properly
            import socks
            socks.set_default_proxy(
                socks.SOCKS5,
                self.connection['host'],
                self.connection['port']
            )
            socket.socket = socks.socksocket
            self.server = smtplib.SMTP(timeout=20)
        return self.server

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.server.quit()
        except:
            pass
        if self.connection['type'] == 'proxy':
            socks.socksocket.default_proxy = None