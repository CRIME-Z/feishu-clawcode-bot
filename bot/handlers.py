"""消息处理器"""
import json
import logging
from typing import Tuple, Optional
from clawcode_engine import ClawCodeExecutor
from feishu_client import FeishuClient
from clawcode_engine.parser import truncate

logger = logging.getLogger(__name__)

class MessageHandler:
    """消息处理器"""

    def __init__(self):
        self.clawcode = ClawCodeExecutor()
        self.feishu = FeishuClient()

    def handle_text_message(self, content: dict, event: dict) -> Tuple[bool, str]:
        """
        处理文本消息

        Args:
            content: 消息内容 {"text": "..."}
            event: 事件完整数据

        Returns:
            (是否成功, 回复文本)
        """
        user_text = content.get("text", "").strip()
        if not user_text:
            return False, "空消息"

        chat_id = event.get("chat_id", "")
        sender = event.get("sender", {}).get("sender_id", {}).get("open_id", "")

        logger.info(f"收到消息 from {{sender}}: {{user_text[:50]}}")

        # 调用 ClawCode 处理
        if self.clawcode.is_available():
            result = self.clawcode.execute(user_text, timeout=120)
            reply_text = truncate(result, 2000)
        else:
            reply_text = "ClawCode 未配置，无法处理消息"

        # 发送回复
        if chat_id:
            try:
                self.feishu.send_text_message(chat_id, reply_text, msg_type="chat_id")
                logger.info(f"已回复到 chat_id: {{chat_id}}")
                return True, reply_text
            except Exception as e:
                logger.error(f"发送失败: {{e}}")
                return False, f"发送失败: {{e}}"

        return False, "未找到 chat_id"

    def handle_event(self, data: dict) -> Optional[str]:
        """
        处理飞书事件

        Args:
            data: 事件数据

        Returns:
            错误信息，无错误返回 None
        """
        try:
            event = data.get("header", {})
            event_type = event.get("event_type")
            event_data = event.get("event", {})

            if event_type == "im.message.receive_v1":
                msg_type = event_data.get("msg_type")
                msg_content = json.loads(event_data.get("content", "{}"))

                if msg_type == "text":
                    success, _ = self.handle_text_message(msg_content, event_data)
                    return None if success else "处理失败"

            return None

        except Exception as e:
            logger.error(f"处理事件失败: {{e}}")
            return str(e)
