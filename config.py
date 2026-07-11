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

# ── 專業術語清單 ──────────────────────────────────────────────────────────────
# 在這裡加你常用的中英夾雜術語，辨識 prompt 和 AI 潤稿都會用到。
# 以後要新增術語，只要改這個 list 就好。
TERMS = [
    "zone2", "zone 2", "pace", "DRAM", "call", "put",
    "API", "component", "refactor", "PR", "commit", "deploy",
    "backend", "frontend", "database", "server", "client",
]

# 給 Whisper 的辨識提示（自動帶入術語清單）
# 注意：Whisper 的 prompt 不是「指令」，它會把這段文字當成「前一段逐字稿」來模仿風格。
# 所以要寫成自然的繁體中文句子（讓它模仿繁體），並把術語自然地放進句子裡。
INITIAL_PROMPT = (
    "嗯，好，那我們繼續。"
    f"今天會聊到 {'、'.join(TERMS)} 這些東西。"
)

# ── AI 潤稿設定 ───────────────────────────────────────────────────────────────
# 開啟後，會用 LLM 把 Whisper 的原始稿補上正確標點、修正中英術語。
# 只補標點+修術語，不改你的用詞、不刪字。
ENABLE_POLISH = True
POLISH_MODEL = "qwen/qwen3.6-27b"  # 阿里 Qwen，中文標點能力遠勝 Llama

# ── 快捷鍵設定 ────────────────────────────────────────────────────────────────
# 按住 Right Option 錄音，放開後送出
# 可改為 left_option, right_ctrl
HOTKEY = "right_option"

# 靜音偵測：超過這個秒數沒有聲音自動停止（0 = 不自動停止）
SILENCE_TIMEOUT = 0

# 浮動視窗位置 (螢幕底部中央)
WINDOW_Y_OFFSET = 80  # 距離螢幕底部的像素
