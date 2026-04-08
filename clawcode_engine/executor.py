"""ClawCode 执行器封装"""
import subprocess
import os
from typing import Optional
from config import Config

class ClawCodeExecutor:
    """ClawCode 执行器"""

    def __init__(self):
        self.clawcode_path = Config.CLAWCODE_PATH
        self.python_bin = Config.PYTHON_BIN

    def is_available(self) -> bool:
        """检查 ClawCode 是否可用"""
        if not self.clawcode_path:
            return False
        return os.path.exists(self.clawcode_path)

    def execute(self, prompt: str, timeout: int = 120) -> str:
        """
        执行 ClawCode 任务

        Args:
            prompt: 要执行的提示词
            timeout: 超时时间（秒）

        Returns:
            执行结果文本
        """
        if not self.is_available():
            return "ClawCode 未安装或未配置"

        cmd = [
            self.python_bin, "-m", "clawcode",
            "-p", prompt,
            "-q"  # quiet 模式
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.clawcode_path
            )
            output = result.stdout + result.stderr
            return output.strip() if output.strip() else "执行完成，无输出"
        except subprocess.TimeoutExpired:
            return f"执行超时({{timeout}}秒)"
        except FileNotFoundError:
            return f"Python 未找到: {{self.python_bin}}"
        except Exception as e:
            return f"执行失败: {{str(e)}}"

    def execute_stream(self, prompt: str) -> str:
        """流式执行（简化版，返回完整结果）"""
        return self.execute(prompt)
