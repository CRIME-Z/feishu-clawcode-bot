#!/bin/bash
# Feishu + ClawCode Bot 启动脚本

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 加载环境变量
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# 创建虚拟环境（如果需要）
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 验证配置
if [ -z "$FEISHU_APP_ID" ] || [ -z "$FEISHU_APP_SECRET" ]; then
    echo "❌ 错误: 请先配置 .env 文件"
    echo "   复制 .env.example 为 .env 并填入凭证"
    exit 1
fi

echo "✅ 配置检查通过"
echo "启动 Bot..."

# 启动应用
python3 bot/app.py
