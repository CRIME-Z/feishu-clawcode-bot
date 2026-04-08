# Feishu + ClawCode Bot

 🤖 一个可复用的飞书机器人，后端对接 ClawCode (Claude Code 开源版)

## 功能特性

- ✅ 飞书消息接收与回复
- ✅ ClawCode AI 对话集成
- ✅ 支持 200+ 模型（Claude/GPT/MiniMax/Kimi/DeepSeek 等）
- ✅ Webhook 模式，即时响应
- ✅ 配置文件分离，易于部署
- ✅ 完整的错误处理和日志
- ✅ MIT 开源协议

## 项目结构

```
feishu-clawcode-bot/
├── README.md
├── LICENSE
├── requirements.txt
├── .env.example
├── bot/
│   ├── __init__.py
│   ├── app.py              # Flask 主应用
│   ├── routes.py           # 路由定义
│   └── handlers.py         # 消息处理
├── clawcode_engine/
│   ├── __init__.py
│   ├── executor.py         # ClawCode 调用封装
│   └── parser.py          # 结果解析
├── feishu_client/
│   ├── __init__.py
│   ├── client.py          # 飞书 API 客户端
│   └── auth.py           # 认证 Token 管理
├── config/
│   ├── __init__.py
│   └── settings.py        # 配置管理
├── scripts/
│   └── startup.sh         # 启动脚本
└── tests/
    └── test_basic.py     # 单元测试
```

## 快速部署

### 前置要求

- Python 3.12+
- 一个飞书企业应用
- ClawCode（可选，不安装则只调用 API）

### 步骤 1: 克隆项目

```bash
git clone <your-repo>
cd feishu-clawcode-bot
```

### 步骤 2: 安装依赖

```bash
pip install -r requirements.txt
```

### 步骤 3: 配置

复制配置文件:

```bash
cp .env.example .env
```

编辑 `.env` 文件:

```env
FEISHU_APP_ID=cli_xxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
CLAWCODE_PATH=/path/to/clawcode
PYTHON_BIN=/usr/bin/python3.12
HOST=0.0.0.0
PORT=5000
LOG_LEVEL=INFO
```

### 步骤 4: 获取飞书凭证

1. 前往 [飞书开放平台](https://open.feishu.cn/)
2. 创建企业自建应用
3. 获取 App ID 和 App Secret
4. 配置机器人能力
5. 添加权限: `im:message`, `im:message:receive_v1`
6. 设置事件订阅: `im.message.receive_v1`
7. 配置 Webhook 地址: `http://your-server:5000/webhook`

### 步骤 5: 启动

```bash
bash scripts/startup.sh
# 或手动:
python3 bot/app.py
```

### 步骤 6: 验证

在飞书中给机器人发消息，应该能收到回复。

## 使用 Docker 部署

```bash
docker build -t feishu-clawcode-bot .
docker run -d --env-file .env -p 5000:5000 feishu-clawcode-bot
```

## 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| FEISHU_APP_ID | ✅ | 飞书应用 App ID |
| FEISHU_APP_SECRET | ✅ | 飞书应用 App Secret |
| CLAWCODE_PATH | ❌ | ClawCode 安装路径，不填则只用 API |
| PYTHON_BIN | ❌ | Python 路径，默认 python3 |
| HOST | ❌ | 监听地址，默认 0.0.0.0 |
| PORT | ❌ | 监听端口，默认 5000 |
| LOG_LEVEL | ❌ | 日志级别，默认 INFO |

## 开发

### 运行测试

```bash
pytest tests/
```

### 项目模块说明

#### bot/app.py
Flask 主应用，负责:
- Webhook 验证
- 消息接收和路由
- 错误处理

#### clawcode_engine/executor.py
ClawCode 调用封装:
- subprocess 调用 clawcode CLI
- 超时控制
- 结果解析

#### feishu_client/client.py
飞书 API 客户端:
- 获取 tenant_access_token
- 发送消息
- 消息格式化

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 贡献

欢迎提交 Issue 和 Pull Request！
