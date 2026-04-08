"""配置管理"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Config:
    """应用配置"""

    # 飞书凭证
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

    # ClawCode
    CLAWCODE_PATH = os.getenv("CLAWCODE_PATH", "")
    PYTHON_BIN = os.getenv("PYTHON_BIN", "python3.12")

    # 服务
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 验证配置
    @classmethod
    def validate(cls):
        if not cls.FEISHU_APP_ID or not cls.FEISHU_APP_SECRET:
            raise ValueError("FEISHU_APP_ID 和 FEISHU_APP_SECRET 必须配置")
        return True

    # ClawCode 可用性
    @classmethod
    def has_clawcode(cls):
        if not cls.CLAWCODE_PATH:
            return False
        return os.path.exists(cls.CLAWCODE_PATH)
