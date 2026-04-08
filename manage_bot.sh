#!/bin/bash
# Feishu ClawCode Bot 管理脚本
# 用法: ./manage_bot.sh [start|stop|restart|status|logs]

BOT_DIR="/volume1/docker/feishu-clawcode-bot"
LOG_FILE="$BOT_DIR/bot.log"
BOT_SCRIPT="$BOT_DIR/bot/ws_client.py"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

show_status() {
    if pgrep -f "$BOT_SCRIPT" > /dev/null; then
        echo -e "${GREEN}✅ Bot 运行中${NC}"
        pgrep -f "$BOT_SCRIPT" | xargs ps -p | tail -1 | awk '{print "   PID: " $1}'
    else
        echo -e "${RED}❌ Bot 未运行${NC}"
    fi
}

case "$1" in
    start)
        echo "启动 Bot..."
        cd "$BOT_DIR"
        nohup python3 bot/ws_client.py > bot.log 2>&1 &
        sleep 2
        show_status
        ;;
    stop)
        echo "停止 Bot..."
        pkill -f "$BOT_SCRIPT"
        echo -e "${GREEN}✅ Bot 已停止${NC}"
        ;;
    restart)
        echo "重启 Bot..."
        pkill -f "$BOT_SCRIPT" 2>/dev/null
        sleep 2
        cd "$BOT_DIR"
        nohup python3 bot/ws_client.py > bot.log 2>&1 &
        sleep 3
        show_status
        ;;
    status)
        show_status
        ;;
    logs)
        echo "最近的日志:"
        tail -30 "$LOG_FILE"
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac

exit 0
