"""
Feishu + ClawCode Bot - V2 长连接模式
整合架构：Flask/WebSocket + ACP Agent + Per-Session 队列 + 看门狗

设计理念：
- ACP 持久进程：session 管理在 Rust 端，更原生
- Per-Session 并行：同一 session 串行，不同 session 并行
- 看门狗：5分钟沉默自动重启
- 模块化：clawcode_engine/ 负责所有执行逻辑
"""
import os
import sys
import json
import logging
import ssl
import threading
import time
import atexit

# 路径处理
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# OpenClaw 风格去重模块
import dedup

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


# =============================================================================
# 去重模块
# =============================================================================

_dedupe = None


def _init_dedup():
    global _dedupe
    dedup_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
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


# =============================================================================
# 辅助函数
# =============================================================================


def truncate(text: str, max_length: int = 4000) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n[...还有 {len(text) - max_length} 字符]"


# =============================================================================
# 事件处理器
# =============================================================================


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

                # ------------------------------------------------
                # V2: 消息加入 Per-Session 队列
                # ------------------------------------------------
                session_id = chat_id  # 以 chat_id 作为 session_id

                if bot_instance.executor_v2.is_available():
                    bot_instance.executor_v2.enqueue(
                        session_id=session_id,
                        chat_id=chat_id,
                        text=text,
                        msg_id=message_id
                    )
                else:
                    # Executor 未启动，发送错误提示
                    bot_instance.send_message(
                        chat_id,
                        "⚠️ ClawCode Agent 未运行，请联系管理员"
                    )

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    # 使用 builder 模式注册事件处理器
    handler = EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(on_message_receive) \
        .build()

    return handler


# =============================================================================
# Bot 主类
# =============================================================================


class FeishuBot:
    """飞书 Bot (长连接模式 V2)"""

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.agent_path = os.getenv("AGENT_PATH", "agent")
        self.agent_env = {
            "AGENT_CODE_API_KEY": os.getenv("AGENT_CODE_API_KEY", ""),
            "AGENT_CODE_API_BASE_URL": os.getenv("AGENT_CODE_API_BASE_URL", ""),
        }

        if not self.app_id or not self.app_secret:
            raise ValueError("FEISHU_APP_ID 和 FEISHU_APP_SECRET 必须配置")

        # ------------------------------------------------
        # V2: 初始化执行器
        # ------------------------------------------------
        from feishu_client import FeishuClient as FeishuClientImpl
        from clawcode_engine import ClawCodeExecutorV2

        self.feishu_client = FeishuClientImpl()
        self.executor_v2 = ClawCodeExecutorV2(
            config={
                "agent_path": self.agent_path,
                "working_dir": os.getcwd(),
                "env": self.agent_env,
                "watchdog_threshold": 300,
                "feishu_client": self.feishu_client,
            }
        )

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
        """发送消息（通过 lark-oapi HTTP client）"""
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

    def start(self):
        """启动 Bot（包含执行器）"""
        # 启动 ACP Agent
        if not self.executor_v2.start():
            logger.error("执行器启动失败，请检查 agent 是否安装")
            return False

        logger.info("执行器启动成功")
        return True

    def stop(self):
        """停止 Bot"""
        logger.info("正在停止 Bot...")
        if self.executor_v2:
            self.executor_v2.stop()


# =============================================================================
# 主函数
# =============================================================================


def main():
    """主函数"""
    print("=" * 50)
    print("  Feishu + ClawCode Bot V2 (长连接模式)")
    print("  架构：ACP Agent + Per-Session 队列 + 看门狗")
    print("=" * 50)
    print(f"  App ID: {os.getenv('FEISHU_APP_ID', '未配置')}")
    print(f"  Agent: {os.getenv('AGENT_PATH', 'agent')}")
    print(f"  API Key: {'✅ 已配置' if os.getenv('AGENT_CODE_API_KEY') else '⚠️ 未配置'}")
    print("=" * 50)

    bot = FeishuBot()

    # 启动执行器
    if not bot.start():
        print("⚠️ 执行器启动失败，但继续启动 Bot...")
    else:
        print("✅ ACP Agent 已启动")

    # 注册退出清理
    atexit.register(bot.stop)

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
    time.sleep(2)

    if t.is_alive():
        print("✅ 客户端已在后台运行，等待消息...")
        print("  (按 Ctrl+C 停止)")
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n正在停止 Bot...")
    else:
        print("⚠️ 客户端已结束")


if __name__ == "__main__":
    main()
