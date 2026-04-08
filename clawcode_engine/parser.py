"""结果解析器"""
import json
import re
from typing import Optional

def parse_code_blocks(text: str) -> list[dict]:
    """解析文本中的代码块"""
    pattern = r"```(\w+)?\n?(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [{"language": lang or "text", "code": code.strip()} for lang, code in matches]

def extract_json(text: str) -> Optional[dict]:
    """尝试从文本中提取 JSON"""
    # 尝试找 ```json ... ```
    json_pattern = r"```json\n?(.*?)\n?```"
    match = re.search(json_pattern, text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def truncate(text: str, max_length: int = 2000) -> str:
    """截断文本"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"\n\n[...还有 {{len(text) - max_length}} 字符]"
