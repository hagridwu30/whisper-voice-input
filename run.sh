#!/bin/bash
# 啟動語音輸入 app
cd "$(dirname "$0")"
source venv/bin/activate
python voice_input.py
