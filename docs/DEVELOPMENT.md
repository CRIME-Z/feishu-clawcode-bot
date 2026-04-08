# 开发文档

## 架构说明

### 模块依赖

```
bot/app.py (Flask)
    └── bot/routes.py
        └── bot/handlers.py
            ├── feishu_client/FeishuClient
            └── clawcode_engine/ClawCodeExecutor
```

### 消息流程

```
飞书 → Webhook → /webhook
                  ↓
           handlers.handle_event()
                  ↓
         ClawCodeExecutor.execute()
                  ↓
         FeishuClient.send_text_message()
                  ↓
               飞书
```

## 扩展开发

### 添加新的消息类型

在 `bot/handlers.py` 的 `handle_event` 方法中添加:

```python
if event_type == "im.message.receive_v1":
    msg_type = event_data.get("msg_type")

    if msg_type == "image":
        # 处理图片消息
        pass
    elif msg_type == "file":
        # 处理文件消息
        pass
```

### 自定义 ClawCode 行为

修改 `clawcode_engine/executor.py` 的 `execute` 方法:

```python
def execute(self, prompt: str, timeout: int = 120) -> str:
    # 添加预处理
    prompt = f"你是一个助手。{{prompt}}"
    # ... 原逻辑
    # 添加后处理
    return result.strip()
```
