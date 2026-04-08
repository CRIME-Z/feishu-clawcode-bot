"""飞书认证 Token 管理"""
import time
import requests
from config import Config

class FeishuAuth:
    """飞书认证 Token 管理"""

    def __init__(self):
        self.app_id = Config.FEISHU_APP_ID
        self.app_secret = Config.FEISHU_APP_SECRET
        self._token = None
        self._token_expires_at = 0

    def get_tenant_token(self) -> str:
        """获取 tenant_access_token，带缓存"""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        data = {"app_id": self.app_id, "app_secret": self.app_secret}

        resp = requests.post(url, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 0:
            raise Exception(f"获取Token失败: {{result}}")

        self._token = result["tenant_access_token"]
        # Token 有效期 2 小时，提前 1 分钟刷新
        self._token_expires_at = time.time() + 2 * 3600 - 60
        return self._token

    def refresh(self):
        """强制刷新 Token"""
        self._token = None
        self._token_expires_at = 0
        return self.get_tenant_token()
