# 設定檔 - 可自由修改

# Groq API Key (從環境變數讀取，不要寫死在這裡)
import os
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# 錄音設定
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1024

# Whisper 設定
WHISPER_MODEL = "whisper-large-v3"
LANGUAGE = "zh"  # 主要語言設中文，Whisper 會自動處理中英夾雜

# 專業術語 prompt - 告訴 Whisper 這些詞要辨識正確
# 格式：用逗號分隔，可以加入常用詞彙
INITIAL_PROMPT = (
    "以下是繁體中文語音，包含中英夾雜的專業術語。"
    "常見術語：zone2, zone 2, pace, DRAM, dram, call, put, "
    "API, component, refactor, PR, commit, deploy, "
    "backend, frontend, database, server, client。"
    "請使用繁體中文輸出，不要使用簡體中文。"
)

# 快捷鍵設定
# 按住 Right Option 錄音，放開後送出
# 可改為 Key.ctrl_r, Key.shift 等
HOTKEY = "right_option"

# 靜音偵測：超過這個秒數沒有聲音自動停止（0 = 不自動停止）
SILENCE_TIMEOUT = 0

# 浮動視窗位置 (螢幕底部中央)
WINDOW_Y_OFFSET = 80  # 距離螢幕底部的像素
