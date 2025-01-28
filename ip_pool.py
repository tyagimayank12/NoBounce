from threading import Lock
import logging
import requests

logger = logging.getLogger(__name__)

class IPPool:
    def __init__(self):
        # Proxy Configuration only
        self.proxy = {
            'host': 'brd.superproxy.io',
            'port': 33335,
            'user': 'brd-customer-hl_9cce9303-zone-residential_proxy1',
            'password': '8yk0bozbuef7',
            'url': 'http://brd-customer-hl_9cce9303-zone-residential_proxy1:8yk0bozbuef7@brd.superproxy.io:33335'
        }
        self.lock = Lock()
        self.logger = logging.getLogger(__name__)

    def get_connection(self):
        """Only return proxy configuration"""
        with self.lock:
            return {
                'type': 'proxy',
                'config': self.proxy
            }

    def get_status(self):
        """Return proxy status"""
        return {
            "proxy_enabled": True,
            "proxy_config": {
                "host": self.proxy['host'],
                "port": self.proxy['port']
            }
        }

    def test_proxy(self):
        """Test if proxy is working"""
        try:
            proxies = {
                'http': self.proxy['url'],
                'https': self.proxy['url']
            }
            response = requests.get(
                'https://api.ipify.org?format=json',
                proxies=proxies,
                verify=False,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Proxy test failed: {str(e)}")
            return False