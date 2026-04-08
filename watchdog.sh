#!/bin/bash
LOG="$HOME/clawcode/feishu-clawcode-bot/watchdog.log"
BOT_DIR="$HOME/clawcode/feishu-clawcode-bot"
PYTHON="/usr/local/bin/python3"

echo "$(date): Watchdog starting" >> $LOG

while true; do
    echo "$(date): Starting bot..." >> $LOG
    cd "$BOT_DIR"
    PYTHONPATH="$BOT_DIR" "$PYTHON" bot/app.py >> "$BOT_DIR/bot.log" 2>&1
    EXIT=$?
    echo "$(date): Bot exited with code $EXIT, restarting in 5s..." >> $LOG
    sleep 5
done
