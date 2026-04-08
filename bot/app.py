"""
Feishu + ClawCode Bot - 长连接模式
使用 lark-oapi SDK 的 WebSocket 客户端
"""
import os
import sys
import json
import logging
import ssl
import threading
import time
import atexit

# OpenClaw 风格去重模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dedup
from collections import defaultdict

# 全局禁用 SSL 验证（如需代理访问外网）
_orig_ssl_create_default_context = ssl.create_default_context
def _patched_create_default_context(*args, **kwargs):
    ctx = _orig_ssl_create_default_context(*args, **kwargs)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
ssl.create_default_context = _patched_create_default_context

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class ClawCodeExecutor:
    """ClawCode 执行器"""

    def __init__(self, clawcode_path: str = ""):
        self.clawcode_path = clawcode_path or os.getenv("CLAWCODE_PATH", "")
        self.available = self._check_available()

    def _check_available(self) -> bool:
        if not self.clawcode_path:
            return False
        return os.path.exists(self.clawcode_path)

    def is_available(self) -> bool:
        return self.available

    def execute(self, prompt: str, timeout: int = 120) -> str:
        """执行 ClawCode 命令"""
        if not self.is_available():
            return "ClawCode 未配置"

        import subprocess
        try:
            result = subprocess.run(
                ["/usr/local/bin/python3", "-m", "clawcode", "-p", prompt, "-q"],
                cwd=self.clawcode_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout or result.stderr or "无输出"
        except subprocess.TimeoutExpired:
            return "执行超时"
        except Exception as e:
            return f"执行失败: {str(e)}"


def truncate(text: str, max_length: int = 2000) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n[...还有 {len(text) - max_length} 字符]"


# OpenClaw 风格去重：两层检查（内存 + 磁盘）+ 文件锁 + 原子写入
_dedupe = None

def _init_dedup():
    global _dedupe
    dedup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    _dedupe = dedup.PersistentDedupe(
        dedup_dir=dedup_dir,
        ttl_ms=1440 * 60 * 1000,  # 24小时
        memory_max_size=10000,
        file_max_entries=50000,
        namespace="clawcode"
    )
    loaded = _dedupe.warmup()
    logger.info(f"[Dedup] 加载了 {loaded} 条去重记录，窗口 24h")

_init_dedup()


def create_event_handler(bot_instance: "FeishuBot"):
    """创建正确格式的 EventDispatcherHandler"""
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
    from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

    def on_message_receive(event: P2ImMessageReceiveV1):
        """处理收到的消息"""
        try:
            message = event.event.message
            if message is None:
                return

            msg_type = message.message_type
            chat_id = message.chat_id
            content_str = message.content
            message_id = message.message_id

            # OpenClaw 风格去重：内存+磁盘两层检查
            if _dedupe.check_and_record(message_id):
                logger.info(f"跳过重复消息: message_id={message_id}")
                return

            logger.info(f"收到消息: type={msg_type}, chat_id={chat_id}, msg_id={message_id}")

            if msg_type == "text":
                # 解析文本内容
                try:
                    content = json.loads(content_str) if content_str else {}
                except:
                    content = {"text": content_str or ""}

                text = content.get("text", "").strip()
                if not text:
                    return

                logger.info(f"消息内容: {text[:100]}")

                # 调用 ClawCode 处理
                if bot_instance.clawcode.is_available():
                    result = bot_instance.clawcode.execute(text, timeout=120)
                    reply_text = truncate(result, 2000)
                else:
                    reply_text = "ClawCode 未配置，当前为演示模式"

                # 发送回复
                if chat_id:
                    bot_instance.send_message(chat_id, reply_text)

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    # 使用 builder 模式注册事件处理器
    handler = EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message_receive) \
        .build()

    return handler


class FeishuBot:
    """飞书 Bot (长连接模式)"""

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.clawcode = ClawCodeExecutor()

        if not self.app_id or not self.app_secret:
            raise ValueError("FEISHU_APP_ID 和 FEISHU_APP_SECRET 必须配置")

        # 创建 HTTP API client（用于发送消息）
        from lark_oapi.client import Client as HttpClient
        self.http_client = HttpClient.builder() \
            .app_id(self.app_id) \
            .app_secret(self.app_secret) \
            .build()

    def create_client(self):
        """创建 lark-oapi WebSocket 客户端"""
        from lark_oapi.ws.client import Client as WsClient
        from lark_oapi import LogLevel

        # 创建事件处理器
        event_handler = create_event_handler(self)

        return WsClient(
            self.app_id,
            self.app_secret,
            log_level=LogLevel.INFO,
            event_handler=event_handler
        )

    def send_message(self, chat_id: str, text: str) -> None:
        """发送消息"""
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest
            from lark_oapi.api.im.v1.model import CreateMessageRequestBody

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                        .content(json.dumps({"text": text}))
                        .msg_type("text")
                        .receive_id(chat_id)
                        .build()
                ) \
                .build()

            resp = self.http_client.im.v1.message.create(request)

            if resp.code == 0:
                logger.info(f"消息发送成功: chat_id={chat_id}")
            else:
                logger.error(f"消息发送失败: code={resp.code}, msg={resp.msg}")

        except Exception as e:
            logger.error(f"发送消息异常: {e}", exc_info=True)


def main():
    """主函数"""
    print("=" * 50)
    print("  Feishu + ClawCode Bot (长连接模式)")
    print("=" * 50)
    print(f"  App ID: {os.getenv('FEISHU_APP_ID', '未配置')}")
    print(f"  ClawCode: {'✅ 已配置' if os.path.exists(os.getenv('CLAWCODE_PATH', '')) else '⚠️ 未配置'}")
    print("=" * 50)
    print("  使用 WebSocket 长连接模式")
    print("  无需公网地址，直接连接飞书服务器")
    print("=" * 50)

    bot = FeishuBot()
    client = bot.create_client()

    print("\n正在连接飞书服务器...")

    # 在独立线程中启动 client.start()（它内部会阻塞）
    def run_client():
        try:
            client.start()
        except Exception as e:
            print(f"[ERROR] client.start() 异常: {e}")

    t = threading.Thread(target=run_client)
    t.daemon = True
    t.start()

    # 等待线程启动
    import time
    time.sleep(2)

    if t.is_alive():
        print("✅ 客户端已在后台运行，等待消息...")
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在停止 Bot...")
    else:
        print("⚠️ 客户端已结束")


if __name__ == "__main__":
    main()
