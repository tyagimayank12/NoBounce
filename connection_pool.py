import smtplib
from threading import Lock
from collections import deque
from datetime import datetime


class SMTPConnectionPool:
    def __init__(self, max_connections=5, cooldown_minutes=5):
        self.max_connections = max_connections
        self.cooldown_minutes = cooldown_minutes
        self.connections = deque(maxlen=max_connections)
        self.lock = Lock()
        self.last_used = {}
        self.connection_attempts = {}

    def get_connection(self, domain):
        with self.lock:
            now = datetime.now()
            self._cleanup_old_connections(now)

            if domain in self.last_used:
                time_diff = (now - self.last_used[domain]).total_seconds() / 60
                if time_diff < self.cooldown_minutes:
                    raise Exception(f"Domain {domain} in cooldown period")

            connection = self._get_or_create_connection(domain)
            self.last_used[domain] = now
            return connection

    def _cleanup_old_connections(self, now):
        expired = []
        for domain, last_time in self.last_used.items():
            if (now - last_time).total_seconds() / 60 > self.cooldown_minutes:
                expired.append(domain)

        for domain in expired:
            del self.last_used[domain]
            if domain in self.connection_attempts:
                del self.connection_attempts[domain]

    def _get_or_create_connection(self, domain):
        try:
            server = smtplib.SMTP(timeout=10)
            server.set_debuglevel(False)
            return server
        except Exception as e:
            self.connection_attempts[domain] = self.connection_attempts.get(domain, 0) + 1
            raise Exception(f"Failed to create SMTP connection for {domain}")
