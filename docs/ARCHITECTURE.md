# 架构设计 V2

## 整体架构

```
飞书 WebSocket → bot/app.py → clawcode_engine/
                                          │
                    ┌─────────────────────┴─────────────────────┐
                    │                                          │
              ClawCodeExecutorV2                        FeishuClient
                    │
        ┌───────────┼───────────┐
        │           │           │
   ACPAgent    QueueManager  Watchdog
        │
   agent --acp (Rust 持久进程)
        │
   MiniMax API
```

## 核心模块

### clawcode_engine/acp_agent.py

ACP 持久进程管理器，通过 JSON-RPC 2.0 与 `agent --acp` 通信。

- **持久进程**：`subprocess.Popen` 常驻，不每次请求新建进程
- **非阻塞读取**：`select` + `O_NONBLOCK` 实时读取 stdout
- **看门狗集成**：任何输出都触发 `watchdog.record_output()`
- **自动重连**：看门狗超时后自动 `restart()`

```python
agent = ACPAgent(
    agent_path="agent",
    working_dir="/path/to/workdir",
    env={"AGENT_CODE_API_KEY": "..."},
    watchdog_threshold=300,  # 5分钟沉默阈值
)
agent.start()
response = agent.send_message("Hello", session_id="session-xxx")
```

### clawcode_engine/queue_manager.py

Per-Session 并行队列。

- **同一 session**：串行处理（FIFO）
- **不同 session**：完全并行
- **独立线程**：每个 session 有自己的处理线程
- **无锁竞争**：只有访问自己的队列需要锁

```python
def worker(session_id, chat_id, text, msg_id):
    # 处理逻辑
    pass

qm = QueueManager(worker_fn=worker)
qm.enqueue("session-1", "chat-xxx", "Hello", "msg-xxx")
```

### clawcode_engine/watchdog.py

沉默看门狗，检测进程卡住并自动重启。

- **实时监控**：每 10 秒检查一次
- **追踪输出**：每次 `record_output()` 重置计时器
- **超阈值**：5 分钟无任何输出 → SIGKILL 进程组
- **回调通知**：超时后调用 `on_timeout()` 重新启动

### clawcode_engine/executor_v2.py

整合层，对外提供统一接口。

- 启动时创建 `ACPAgent` + `QueueManager`
- 设置 `FeishuClient` 用于回复消息
- `enqueue()` 将消息加入队列，自动分发到对应 session

### bot/app.py

飞书 Bot 主入口（V2）。

- 使用 lark-oapi WebSocket 长连接
- 消息去重（内存 + 磁盘两层）
- 调用 `ClawCodeExecutorV2.enqueue()` 入队
- 启动/停止时管理执行器生命周期

## 与 V1 的区别

| | V1 | V2 |
|--|----|----|
| 进程模型 | 每次 `subprocess.run()` | `subprocess.Popen` 常驻 |
| Session | 无状态 | ACP 原生管理 |
| 并行 | 无 | Per-session 并行 |
| 响应 | 一次性返回 | 可流式 |
| 看门狗 | 无 | 5分钟沉默自动重启 |
| 重连 | 手动 | 自动 |

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_APP_ID` | ✅ | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | ✅ | 飞书应用 App Secret |
| `AGENT_CODE_API_KEY` | ✅ | MiniMax API Key |
| `AGENT_CODE_API_BASE_URL` | ✅ | API 地址（默认 MiniMax） |
| `AGENT_PATH` | ❌ | agent 命令路径（默认 "agent"） |
| `LOG_LEVEL` | ❌ | 日志级别（默认 INFO） |

## 启动流程

```bash
# 1. 确保 agent 已安装
cargo install agent-code

# 2. 配置环境变量
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export AGENT_CODE_API_KEY=sk-cp-xxx
export AGENT_CODE_API_BASE_URL=https://api.minimaxi.com

# 3. 启动
python bot/app.py
```
