"""飞书 API 客户端"""
import json
import requests
from typing import Optional
from .auth import FeishuAuth

class FeishuClient:
    """飞书 API 客户端"""

    def __init__(self):
        self.auth = FeishuAuth()

    def send_text_message(self, receive_id: str, text: str, msg_type: str = "open_id") -> dict:
        """
        发送文本消息

        Args:
            receive_id: 接收者 ID (open_id/user_id/chat_id)
            text: 消息文本
            msg_type: 接收者类型 (open_id/user_id/chat_id)

        Returns:
            API 响应结果
        """
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        token = self.auth.get_tenant_token()

        headers = {
            "Authorization": f"Bearer {{token}}",
            "Content-Type": "application/json"
        }

        params = {"receive_id_type": msg_type}
        data = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }

        resp = requests.post(url, headers=headers, params=params, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def reply_message(self, message_id: str, text: str) -> dict:
        """
        回复消息（通过 message_id）

        Args:
            message_id: 消息 ID
            text: 回复文本

        Returns:
            API 响应结果
        """
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{{message_id}}/reply"
        token = self.auth.get_tenant_token()

        headers = {
            "Authorization": f"Bearer {{token}}",
            "Content-Type": "application/json"
        }

        data = {
            "msg_type": "text",
            "content": json.dumps({"text": text})
        }

        resp = requests.post(url, headers=headers, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
