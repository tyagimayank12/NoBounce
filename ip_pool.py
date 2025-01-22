from collections import deque
from threading import Lock
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class IPPool:
    def __init__(self, ips=None, requests_per_ip=100, cooldown_minutes=15):
        self.ips = deque(ips or [
            '13.61.64.236',  # Original IP
            '13.60.65.138',
            '13.61.100.159',
            '13.53.128.166'
        ])
        self.lock = Lock()
        self.current_ip_usage = {}
        self.last_used = {}
        self.cooldown_minutes = cooldown_minutes
        self.requests_per_ip = requests_per_ip  # Reduced from 200 to 100 for safety

    def get_next_ip(self):
        with self.lock:
            now = datetime.now()

            # Try all IPs
            for _ in range(len(self.ips)):
                ip = self.ips[0]

                # Check if IP is in cooldown
                if ip in self.last_used:
                    time_since_last_use = (now - self.last_used[ip]).total_seconds() / 60
                    if time_since_last_use < self.cooldown_minutes:
                        logger.info(
                            f"IP {ip} in cooldown. {self.cooldown_minutes - time_since_last_use:.1f} minutes remaining")
                        self.ips.rotate(-1)
                        continue

                # Check usage count
                usage_count = self.current_ip_usage.get(ip, 0)
                if usage_count >= self.requests_per_ip:
                    logger.info(f"IP {ip} reached limit. Rotating to next IP")
                    self.ips.rotate(-1)
                    continue

                # IP is available
                self.current_ip_usage[ip] = usage_count + 1
                self.last_used[ip] = now

                # If this IP is near its limit, rotate it to the back
                if self.current_ip_usage[ip] >= self.requests_per_ip:
                    self.ips.rotate(-1)

                logger.info(f"Using IP: {ip} (Usage: {self.current_ip_usage[ip]}/{self.requests_per_ip})")
                return ip

            # If we get here, all IPs are either in cooldown or at limit
            earliest_available = min(
                (ip for ip in self.ips if ip in self.last_used),
                key=lambda ip: self.last_used[ip]
            )
            cooldown_remaining = (self.cooldown_minutes * 60) - (
                    datetime.now() - self.last_used[earliest_available]
            ).total_seconds()

            raise Exception(
                f"All IPs are in cooldown. Please wait {cooldown_remaining:.0f} seconds"
            )

    def release_ip(self, ip):
        with self.lock:
            # Reset usage if IP has been in cooldown
            if ip in self.last_used:
                time_since_last_use = (datetime.now() - self.last_used[ip]).total_seconds() / 60
                if time_since_last_use >= self.cooldown_minutes:
                    self.current_ip_usage[ip] = 0

    def get_status(self):
        with self.lock:
            now = datetime.now()
            return {
                "ips": [{
                    "ip": ip,
                    "usage": self.current_ip_usage.get(ip, 0),
                    "limit": self.requests_per_ip,
                    "in_cooldown": ip in self.last_used and (
                            now - self.last_used[ip]
                    ).total_seconds() / 60 < self.cooldown_minutes,
                    "cooldown_remaining": round(
                        self.cooldown_minutes - (
                                now - self.last_used[ip]
                        ).total_seconds() / 60
                    ) if ip in self.last_used else 0
                } for ip in self.ips]
            }