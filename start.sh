#!/bin/bash
cd /Users/crime/feishu-clawcode-bot
export PYTHONPATH=/Users/crime/feishu-clawcode-bot
nohup python3 bot/app.py > bot.log 2>&1 &
echo "Bot started with PID: $!"
