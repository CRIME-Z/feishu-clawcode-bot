"""
Feishu + ClawCode Bot - 入口文件
支持两种模式:
- ws: WebSocket 长连接模式 (默认，推荐)
- http: Flask HTTP Webhook 模式
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# 检查运行模式
BOT_MODE = os.getenv("BOT_MODE", "ws").lower()

if BOT_MODE == "ws":
    # WebSocket 长连接模式
    from bot.ws_client import main
    if __name__ == "__main__":
        main()
else:
    # HTTP Webhook 模式 (需要公网地址)
    from bot.app import create_app
    import logging

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    app = create_app()

    if __name__ == "__main__":
        print("=" * 50)
        print("  Feishu + ClawCode Bot")
        print("  HTTP Webhook 模式")
        print("=" * 50)
        print("⚠️  警告: 此模式需要公网地址!")
        print("=" * 50)
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=False)
