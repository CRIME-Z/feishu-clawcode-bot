"""
Feishu + ClawCode Bot - 长连接模式
使用 lark-oapi SDK 的 WebSocket 客户端

功能：
- 收到消息后发送"正在处理中"提示
- 直接调用 ClawCode 处理（不通过 SSH）
- 处理完成后发送结果
- 消息队列确保顺序处理
- 基于 message_id 去重
"""
import os
import sys

# 第一个清除所有代理环境变量（必须在 import 其他模块之前）
for key in list(os.environ.keys()):
    if 'proxy' in key.lower():
        del os.environ[key]
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
os.environ['CURL_CA_BUNDLE'] = '/etc/ssl/cert.pem'
os.environ['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
os.environ['SSL_CERT_DIR'] = '/etc/ssl'
os.environ['REQUESTS_CA_BUNDLE'] = '/etc/ssl/cert.pem'

# 禁用 SSL 验证（避免 v2ray SSL 拦截问题）
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import json
import logging
import threading
import time
import asyncio

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
    """ClawCode 执行器 - 直接调用 ClawCode 库"""

    def __init__(self):
        self.clawcode_path = os.getenv("CLAWCODE_PATH", "/Users/crime/clawcode")
        self.available = self._check_available()
        self._session_id = None  # 保持会话

    def _check_available(self) -> bool:
        """检查 ClawCode 是否可用"""
        try:
            sys.path.insert(0, self.clawcode_path)
            from clawcode.app import create_app
            return True
        except Exception as e:
            logger.error(f"检查 ClawCode 可用性失败: {e}")
            return False

    def is_available(self) -> bool:
        return self.available

    def execute(self, prompt: str, timeout: int = 120) -> str:
        """直接调用 ClawCode 处理"""
        if not self.is_available():
            return "❌ ClawCode 未配置"

        try:
            # 添加 clawcode 到 path
            if self.clawcode_path not in sys.path:
                sys.path.insert(0, self.clawcode_path)

            import asyncio
            from clawcode.app import create_app
            from clawcode.llm.agent import Agent, AgentEventType
            from clawcode.llm.providers import create_provider, resolve_provider_from_model
            from clawcode.llm.tools import get_builtin_tools

            async def run():
                try:
                    logger.info(f"开始创建 app context, working_dir={self.clawcode_path}")
                    app_ctx = await create_app(working_dir=self.clawcode_path, debug=False)
                    logger.info(f"App context 创建成功")
                    
                    settings = app_ctx.settings
                    session_service = app_ctx.session_service
                    message_service = app_ctx.message_service

                    # 检查 settings
                    agent_config = settings.get_agent_config("coder")
                    logger.info(f"Agent model: {agent_config.model}, provider_key: {agent_config.provider_key}")
                    
                    # 复用 session（如果没有就创建）
                    if self._session_id is None:
                        session = await session_service.create(f"Feishu Bot: {prompt[:50]}")
                        self._session_id = session.id
                        logger.info(f"创建新 session: {self._session_id}")
                    else:
                        session = await session_service.get(self._session_id)
                        if session is None:
                            session = await session_service.create(f"Feishu Bot: {prompt[:50]}")
                            self._session_id = session.id
                        logger.info(f"复用 session: {self._session_id}")

                    provider_name, provider_key = resolve_provider_from_model(
                        agent_config.model,
                        settings,
                        agent_config,
                    )
                    logger.info(f"Provider resolved: name={provider_name}, key={provider_key}")
                    provider_cfg = settings.providers.get(provider_key)
                    api_key = getattr(provider_cfg, "api_key", None) if provider_cfg else None
                    base_url = getattr(provider_cfg, "base_url", None) if provider_cfg else None

                    provider = create_provider(
                        provider_name=provider_name,
                        model_id=agent_config.model,
                        api_key=api_key,
                        base_url=base_url,
                    )

                    pm = getattr(app_ctx, "plugin_manager", None)
                    hook_engine = pm.hook_engine if pm else None

                    tools = get_builtin_tools(
                        permissions=None,
                        session_service=session_service,
                        message_service=message_service,
                        plugin_manager=pm,
                    )

                    agent = Agent(
                        provider=provider,
                        tools=tools,
                        message_service=message_service,
                        session_service=session_service,
                        hook_engine=hook_engine,
                        settings=settings,
                    )

                    # 处理 prompt
                    logger.info(f"开始处理 prompt: {prompt[:30]}")
                    content = ""
                    event_count = 0
                    async for event in agent.run(session.id, prompt):
                        event_count += 1
                        if event.type == AgentEventType.RESPONSE:
                            if event.message:
                                content = event.message.content or ""
                                logger.info(f"收到 RESPONSE: {content[:50] if content else 'empty'}")
                        elif event.type == AgentEventType.CONTENT_DELTA:
                            content += event.content or ""
                        elif event.type == AgentEventType.ERROR:
                            logger.error(f"Agent error: {event.error}")
                    
                    logger.info(f"处理完成，共 {event_count} 个事件")
                    return content
                except Exception as e:
                    logger.error(f"run() 内部错误: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return f"❌ 内部错误: {str(e)}"

            # 运行异步代码
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(run())
                logger.info(f"执行结果: {repr(result[:50] if result else 'empty')}")
                return result or "⚠️ 无输出"
            except Exception as e:
                logger.error(f"执行 ClawCode 失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return f"❌ 执行失败: {str(e)}"
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"execute 顶层失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"❌ 执行失败: {str(e)}"


def truncate(text: str, max_length: int = 1800) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n...还有 {len(text) - max_length} 字符"


class FeishuBot:
    """飞书 Bot"""

    def __init__(self, app_id: str, app_secret: str, clawcode: ClawCodeExecutor):
        self.app_id = app_id
        self.app_secret = app_secret
        self.clawcode = clawcode

        # 创建 API 客户端
        from lark_oapi import Client
        from lark_oapi.api.im.v1 import CreateMessageRequest, PatchMessageRequest
        from lark_oapi.api.im.v1.model import CreateMessageRequestBody

        self.client = Client.builder().app_id(app_id).app_secret(app_secret).build()
        self.CreateMessageRequest = CreateMessageRequest
        self.PatchMessageRequest = PatchMessageRequest
        self.CreateMessageRequestBody = CreateMessageRequestBody

        # 消息队列
        self.message_queue = []
        self.is_processing = False
        self.queue_lock = threading.Lock()

        # 去重：基于 message_id 去重
        self.processed_ids = {}  # {msg_id: timestamp}
        self.dedup_ttl = 300  # 5分钟内相同ID视为重复

    def _clean_processed_ids(self):
        """清理过期的消息ID记录"""
        now = time.time()
        expired = [mid for mid, ts in self.processed_ids.items() if now - ts > self.dedup_ttl]
        for mid in expired:
            del self.processed_ids[mid]

    def send_text_message(self, chat_id: str, text: str) -> str:
        """发送文本消息"""
        try:
            request = (
                self.CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    self.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )

            resp = self.client.im.v1.message.create(request)
            if resp.code == 0:
                logger.info(f"消息发送成功")
                return resp.data.message_id if resp.data else ""
            else:
                logger.error(f"发送失败: {resp.msg}")
                return ""
        except Exception as e:
            logger.error(f"发送消息异常: {e}")
            return ""

    def send_interactive_card(self, chat_id: str, card_data: dict) -> str:
        """发送交互卡片消息"""
        try:
            card_content = json.dumps(card_data, ensure_ascii=False)

            request = (
                self.CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    self.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(card_content)
                    .build()
                )
                .build()
            )

            resp = self.client.im.v1.message.create(request)
            if resp.code == 0:
                logger.info(f"卡片消息发送成功")
                return resp.data.message_id if resp.data else ""
            else:
                logger.error(f"卡片发送失败: {resp.msg}")
                return ""
        except Exception as e:
            logger.error(f"发送卡片异常: {e}")
            return ""

    def update_card_message(self, message_id: str, card_data: dict) -> bool:
        """更新卡片消息（同一消息展开效果）"""
        try:
            from lark_oapi.api.im.v1.model.patch_message_request_body import PatchMessageRequestBody

            card_content = json.dumps(card_data, ensure_ascii=False)

            request = (
                self.PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(card_content)
                    .build()
                )
                .build()
            )

            resp = self.client.im.v1.message.patch(request)
            if resp.code == 0:
                logger.info(f"卡片消息更新成功")
                return True
            else:
                logger.error(f"卡片更新失败: {resp.msg}")
                return False
        except Exception as e:
            logger.error(f"更新卡片异常: {e}")
            return False

    def build_simple_card(self, title: str, title_color: str, content: str, updatable: bool = False) -> dict:
        """构建简单卡片"""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": title_color
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content
                }
            ]
        }
        if updatable:
            card["config"]["update_multi"] = True
        return card

    def handle_message(self, event, data):
        """处理消息（加入队列）"""
        try:
            message = event.message
            msg_type = message.message_type
            msg_id = message.message_id
            content_str = message.content
            chat_id = message.chat_id
            user_text = content_str

            # 解析内容
            try:
                content = json.loads(content_str)
                user_text = content.get("text", "").strip()
            except:
                pass

            if msg_type == "text" and user_text:
                sender_id = event.sender.sender_id.open_id
                logger.info(f"收到消息 msg_id={msg_id} from {sender_id}: {user_text[:50]}")

                # 基于 message_id 去重
                with self.queue_lock:
                    self._clean_processed_ids()

                    if msg_id in self.processed_ids:
                        logger.warning(f"跳过重复消息 msg_id={msg_id}")
                        return

                    # 记录消息ID
                    self.processed_ids[msg_id] = time.time()

                    # 加入队列
                    self.message_queue.append({
                        "chat_id": chat_id,
                        "user_text": user_text,
                        "sender_id": sender_id,
                        "msg_id": msg_id
                    })
                    logger.info(f"消息加入队列，当前队列长度: {len(self.message_queue)}")

                    # 如果没有在处理，则开始处理
                    if not self.is_processing:
                        self.is_processing = True
                        # 在新线程中处理，避免阻塞
                        thread = threading.Thread(target=self._process_queue)
                        thread.daemon = True
                        thread.start()

        except Exception as e:
            logger.error(f"处理消息失败: {e}")

    def _process_queue(self):
        """处理队列（在线程中运行）"""
        while True:
            task = None
            with self.queue_lock:
                if self.message_queue:
                    task = self.message_queue.pop(0)
                    logger.info(f"开始处理消息: {task['user_text'][:50]}, 队列剩余: {len(self.message_queue)}")
                else:
                    self.is_processing = False
                    break

            if task:
                self._process_single(task)

    def _process_single(self, task):
        """处理单条消息"""
        chat_id = task["chat_id"]
        user_text = task["user_text"]

        try:
            # 1. 发"正在处理中"卡片
            processing_card = self.build_simple_card(
                title="🔄 正在处理",
                title_color="blue",
                content="⏳ 正在思考中，请稍候...",
                updatable=True
            )
            processing_msg_id = self.send_interactive_card(chat_id, processing_card)

            # 2. 调用 ClawCode 处理
            if self.clawcode.is_available():
                result = self.clawcode.execute(user_text, timeout=120)
                reply_text = truncate(result, 1800)
                success = not result.startswith("❌")
                status = "✅ 完成" if success else "❌ 处理失败"
                color = "green" if success else "red"
            else:
                reply_text = "⚠️ ClawCode 未配置，当前为演示模式\n\n你可以发送任意文字测试 bot 是否在线。"
                status = "⚠️ 演示模式"
                color = "grey"

            # 3. 更新卡片
            result_card = self.build_simple_card(
                title=status,
                title_color=color,
                content=reply_text
            )

            if processing_msg_id:
                self.update_card_message(processing_msg_id, result_card)
            else:
                self.send_interactive_card(chat_id, result_card)

        except Exception as e:
            logger.error(f"处理消息异常: {e}")


def main():
    """主函数"""
    print("=" * 50)
    print("  Feishu + ClawCode Bot")
    print("  长连接模式 (WebSocket)")
    print("=" * 50)

    # 检查配置
    app_id = os.getenv("FEISHU_APP_ID", "")
    app_secret = os.getenv("FEISHU_APP_SECRET", "")

    if not app_id or not app_secret:
        print("❌ 错误: FEISHU_APP_ID 和 FEISHU_APP_SECRET 必须配置")
        sys.exit(1)

    print(f"  App ID: {app_id}")
    print(f"  ClawCode: {'✅ 已配置' if os.getenv('CLAWCODE_PATH') else '⚠️ 未配置'}")
    print("=" * 50)
    print("  直接调用 ClawCode（不通过 SSH）")
    print("  消息队列 + message_id去重")
    print("=" * 50)
    print()

    # 创建 ClawCode 执行器
    clawcode = ClawCodeExecutor()
    if clawcode.is_available():
        print("✅ ClawCode 连接成功")
    else:
        print("⚠️ ClawCode 不可用，将使用演示模式")

    # 创建 Bot
    bot = FeishuBot(app_id, app_secret, clawcode)

    # 创建 lark-oapi 客户端
    from lark_oapi import ws, LogLevel
    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

    # 消息处理函数
    def on_message(data):
        try:
            event = data.event
            bot.handle_message(event, data)
        except Exception as e:
            logger.error(f"处理消息异常: {e}")

    # 创建事件处理器
    handler = EventDispatcherHandler.builder(
        encrypt_key="",
        verification_token=""
    ).register_p2_im_message_receive_v1(on_message).build()

    # 创建 WebSocket 客户端
    ws_client = ws.Client(
        app_id,
        app_secret,
        LogLevel.INFO,
        event_handler=handler,
        auto_reconnect=True
    )

    print("正在连接飞书服务器...")

    # 启动客户端
    ws_client.start()

    print("✅ 连接成功!")
    print("正在等待消息...")
    print()

    # 保持运行
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止 Bot...")
        ws_client.stop()
        print("✅ Bot 已停止")


if __name__ == "__main__":
    main()
