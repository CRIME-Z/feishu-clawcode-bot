"""基础测试"""
import pytest
import sys
import os

# 确保项目路径在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_config_import():
    """测试配置导入"""
    from config import Config
    assert Config is not None

def test_feishu_client_import():
    """测试飞书客户端导入"""
    from feishu_client import FeishuClient
    assert FeishuClient is not None

def test_clawcode_executor_import():
    """测试 ClawCode 执行器导入"""
    from clawcode_engine import ClawCodeExecutor
    assert ClawCodeExecutor is not None

def test_parser_functions():
    """测试解析函数"""
    from clawcode_engine.parser import parse_code_blocks, extract_json, truncate

    # 测试代码块解析
    code = "```python\nprint('hello')\n```"
    blocks = parse_code_blocks(code)
    assert len(blocks) == 1
    assert blocks[0]["language"] == "python"

    # 测试截断
    long_text = "a" * 3000
    truncated = truncate(long_text, 100)
    assert len(truncated) < len(long_text)

    # 测试 JSON 解析
    json_text = '''```json
    {"key": "value"}
    '''
    result = extract_json(json_text)
    assert result == {"key": "value"}

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
