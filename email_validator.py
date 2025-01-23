import re
import dns.resolver
import smtplib
import logging
from threading import Lock

class EmailValidator:
    def __init__(self, ips=None):
        self.ips = ips if ips is not None else []
        self.cache = {}
        self.lock = Lock()
        self.email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def is_valid_syntax(self, email: str) -> bool:
        return bool(re.match(self.email_regex, email))

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
                    server.connect(mx_host)
                    server.ehlo()

                    # Use proper sender address
                    server.mail(f'verify@{domain}')
                    code, message = server.rcpt(email)

                    # Only accept definitive success codes
                    if code == 250:
                        return True
                    if code in [550, 551, 553, 554]:
                        return False

                except smtplib.SMTPServerDisconnected:
                    return False
                except smtplib.SMTPResponseException as e:
                    if e.smtp_code in [550, 551, 553, 554]:
                        return False
                    continue
                except Exception:
                    continue
                finally:
                    if server:
                        try:
                            server.quit()
                        except:
                            pass

            return False  # If no MX server accepts, consider invalid

        except Exception:
            return False  # If DNS fails, consider invalid

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