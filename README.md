# VoiceInput 語音輸入

macOS 的語音輸入工具（類似 Typeless / Hex）。**按住 Right Option 說話，放開後文字自動打進游標所在的任何輸入框**。

支援繁體中文（台灣）+ 英文混合輸入，AI 自動補標點符號。

## 功能

- 🎙 **按住即錄**：按住 Right Option 錄音，放開自動辨識並貼入文字
- 🌏 **中英夾雜**：Groq Whisper large-v3 辨識，支援中英混說
- 🇹🇼 **強制繁體**：OpenCC 自動簡轉繁（台灣用語）
- ✨ **AI 潤稿**：Qwen 自動補標點（，。？！）、中英文間加空格，不改動你說的內容
- 📋 **不佔剪貼簿**：貼上後自動還原你原本複製的內容
- 🔁 **開機自啟**：launchd 管理，崩潰自動重開

## 安裝需求

- macOS（Apple Silicon 或 Intel 皆可）
- Python 3.10+（macOS 通常內建，或 `brew install python`）
- [Homebrew](https://brew.sh)
- **Groq API Key**（免費）：到 [console.groq.com](https://console.groq.com) 用 Google 帳號註冊 → API Keys → Create API Key

## 安裝步驟

### 1. 下載專案

有 git：
```bash
git clone https://github.com/hagridwu30/whisper-voice-input.git ~/Projects/whisper-voice-input
```

沒有 git：GitHub 頁面點綠色 **Code → Download ZIP**，解壓縮後把資料夾改名為 `whisper-voice-input`，放到 `~/Projects/` 底下。

### 2. 執行安裝腳本

```bash
bash ~/Projects/whisper-voice-input/install.sh
```

腳本會自動：安裝相依套件 → 詢問並儲存你的 Groq API Key → 建立 `VoiceInput.app` 放到 `~/Applications`。

### 3. 開啟系統權限（必要！）

到 **系統設定 → 隱私權與安全性**：

| 權限 | 開啟對象 |
|------|---------|
| 麥克風 | Python（或 Terminal） |
| 輔助使用（Accessibility） | Python（或 Terminal） |

> 沒開「輔助使用」的話，按 Right Option 會完全沒反應（監聽按鍵需要這個權限）。

### 4. 啟動

雙擊 `~/Applications/VoiceInput.app`，選單列出現 🎙 圖示即成功。

### 5.（可選）開機自動啟動

```bash
cp ~/Projects/whisper-voice-input/com.tedstudio.voiceinput.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tedstudio.voiceinput.plist
```

> ⚠️ plist 裡的路徑寫死為 `/Users/tedstudio/...`，如果你的使用者名稱不同，先打開 plist 把路徑改成你自己的（共 3 處）。

設定後：開機自啟、Mac 喚醒自動恢復、崩潰 10 秒內自動重開。

## 使用方式

1. 游標點進任何輸入框（瀏覽器、備忘錄、聊天軟體都行）
2. **按住 Right Option**，開始說話（螢幕底部出現「🎙 錄音中...」）
3. **放開**，等 1-2 秒文字自動貼入

## 自訂設定（config.py）

### 加專業術語（改善辨識準確率）

打開 `config.py`，把常說的中英夾雜術語加進 `TERMS`：

```python
TERMS = [
    "zone2", "pace", "DRAM", "call", "put",
    "你的新術語",   # ← 直接加在這裡
]
```

辨識和潤稿兩層都會生效。改完重啟 app：`pkill -f voice_input.py`（launchd 會自動重開）。

### 其他選項

| 設定 | 說明 |
|------|------|
| `HOTKEY` | 快捷鍵：`right_option`（預設）/ `left_option` / `right_ctrl` |
| `ENABLE_POLISH` | AI 潤稿開關，`False` 可省 0.3-0.5 秒但沒標點修正 |
| `POLISH_MODEL` | 潤稿模型，預設 `qwen/qwen3.6-27b`（中文標點最好） |

## 常見問題

**按 Right Option 沒反應？**
→ 「輔助使用」權限沒開，或開了之後要重啟 app。若權限列表裡有多個 Python，全部打開。

**換了麥克風（USB/藍牙拔插）後不能用？**
→ app 會自動重試 5 秒偵測新麥克風。還是不行就 `pkill -f voice_input.py` 讓它重啟。

**文字重複輸入兩次？**
→ 舊版 bug，已修（啟動時會自動殺掉舊程序）。確認是最新版。

**出問題想查原因？**
```bash
tail -30 ~/Projects/whisper-voice-input/voice_input.log
```

## 架構

```
按住 Right Option（pynput 監聽）
  → PyAudio 錄音（自動偵測可用麥克風）
  → Groq Whisper large-v3 辨識（語音上雲端）
  → OpenCC 簡轉繁（s2twp）
  → Qwen 潤稿：補標點、修術語拼寫（僅文字上雲端）
  → pbcopy + Cmd+V 貼入游標位置（貼完還原剪貼簿）
```

> 隱私提醒：語音與辨識文字會經過 Groq 雲端處理。Groq 聲明不保留資料，但若有疑慮請勿用於機密內容。
