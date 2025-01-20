from collections import deque
from threading import Lock
from datetime import datetime, timedelta


class IPPool:
    def __init__(self, ips, cooldown_minutes=2):
        self.ips = deque(ips)
        self.lock = Lock()
        self.last_used = {}
        self.cooldown_minutes = cooldown_minutes
        self.attempt_count = {}

    def get_next_ip(self):
        with self.lock:
            now = datetime.now()

            for _ in range(len(self.ips)):
                ip = self.ips[0]
                self.ips.rotate(-1)

                if not self._is_in_cooldown(ip, now):
                    self.last_used[ip] = now
                    self.attempt_count[ip] = self.attempt_count.get(ip, 0) + 1
                    return ip

            raise Exception("All IPs are in cooldown period")

    def _is_in_cooldown(self, ip, now):
        if ip not in self.last_used:
            return False

        attempts = self.attempt_count.get(ip, 0)
        cooldown = self._get_cooldown_period(attempts)
        time_diff = now - self.last_used[ip]

        return time_diff < cooldown

    def _get_cooldown_period(self, attempts):
        if attempts > 100:
            return timedelta(hours=1)
        elif attempts > 50:
            return timedelta(minutes=30)
        elif attempts > 20:
            return timedelta(minutes=10)
        else:
            return timedelta(minutes=self.cooldown_minutes)

    def release_ip(self, ip):
        with self.lock:
            if ip in self.last_used:
                self.last_used[ip] = datetime.now() - timedelta(minutes=self.cooldown_minutes)
