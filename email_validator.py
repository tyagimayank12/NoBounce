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
            mx_records = dns.resolver.resolve(domain, 'MX')
            mx_record = str(mx_records[0].exchange)

            self.logger.info(f"Starting SMTP check for {email} using MX: {mx_record}")

            server = smtplib.SMTP(timeout=30)
            server.set_debuglevel(1)  # Enable detailed SMTP debug logs

            self.logger.info("Connecting to server...")
            server.connect(mx_record)

            self.logger.info("Sending EHLO...")
            server.ehlo()

            self.logger.info("Sending MAIL FROM...")
            from_addr = f"verify@{domain}"
            server.mail(from_addr)

            self.logger.info("Sending RCPT TO...")
            code, message = server.rcpt(email)

            self.logger.info(f"Response code: {code}, Message: {message}")

            return code in [250, 251, 252]

        except Exception as e:
            self.logger.error(f"SMTP Error for {email}: {type(e).__name__}: {str(e)}")
            return True  # Consider valid if check fails
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass

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