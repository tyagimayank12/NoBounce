import re
from datetime import datetime

import dns.resolver
import smtplib
import logging
from threading import Lock

from ip_pool import IPPool


class EmailValidator:
    def __init__(self, ips=None):
        self.ip_pool = IPPool(ips, requests_per_ip=75, cooldown_minutes=15)  # Add this line
        self.cache = {}
        self.lock = Lock()
        self.email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def is_valid_syntax(self, email: str) -> bool:
        return bool(re.match(self.email_regex, email))

    def get_status(self):
        return self.ip_pool.get_status()

    def has_valid_mx_records(self, domain: str) -> bool:
        try:
            mx_records = dns.resolver.resolve(domain, 'MX')
            return len(mx_records) > 0
        except Exception:
            return False

    def smtp_handshake(self, email: str) -> bool:
        domain = email.split('@')[1]
        server = None

        try:
            mx_records = sorted(dns.resolver.resolve(domain, 'MX'),
                                key=lambda x: x.preference)

            for mx in mx_records:
                mx_host = str(mx.exchange).rstrip('.')
                try:
                    server = smtplib.SMTP(timeout=10)
                    server.set_debuglevel(1)

                    response_log = {
                        'mx_host': mx_host,
                        'email': email,
                        'timestamp': datetime.now().isoformat()
                    }

                    server.connect(mx_host)
                    server.ehlo()

                    # Try both domain-specific and generic sender
                    sender_addresses = [
                        f'verify@{domain}',
                        'verify@verify.com'
                    ]

                    for sender in sender_addresses:
                        try:
                            server.mail(sender)
                            code, message = server.rcpt(email)

                            response_log.update({
                                'sender': sender,
                                'code': code,
                                'message': message
                            })
                            self.logger.info(f"SMTP Check: {response_log}")

                            # Definitive success
                            if code == 250:
                                return True

                            # Hard fails
                            if code in [550, 551, 553, 554]:
                                return False

                        except smtplib.SMTPResponseException as e:
                            response_log.update({
                                'error': f"{type(e).__name__}: {str(e)}",
                                'smtp_code': getattr(e, 'smtp_code', None)
                            })
                            self.logger.warning(f"SMTP Error: {response_log}")

                            if getattr(e, 'smtp_code', 0) in [550, 551, 553, 554]:
                                return False
                            continue

                except smtplib.SMTPServerDisconnected:
                    self.logger.error(f"Server disconnected: {mx_host}")
                    return False

                except Exception as e:
                    self.logger.error(f"Error checking {email} on {mx_host}: {str(e)}")
                    continue

                finally:
                    if server:
                        try:
                            server.quit()
                        except:
                            pass

            # No MX server validated the email
            return False

        except Exception as e:
            self.logger.error(f"DNS/General error for {email}: {str(e)}")
            return False

    def validate_email(self, email: str) -> str:
        try:
            if not self.is_valid_syntax(email):
                return 'Invalid Syntax'

            domain = email.split('@')[1]
            if not self.has_valid_mx_records(domain):
                return 'Invalid Domain'

            if not self.smtp_handshake(email):
                return 'SMTP Verification Failed'

            return 'Valid'

        except Exception as e:
            self.logger.error(f"Validation error for {email}: {str(e)}")
            return str(e)