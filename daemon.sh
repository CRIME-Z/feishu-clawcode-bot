#!/bin/bash
cd /Users/crime/clawcode/feishu-clawcode-bot
exec /usr/local/bin/python3 bot/app.py >> /Users/crime/clawcode/feishu-clawcode-bot/daemon.log 2>&1
