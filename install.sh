#!/bin/bash
set -e

echo "🎙 VoiceInput 安裝程式"
echo "====================="

PROJ="$HOME/Projects/whisper-voice-input"

# 1. 建立專案資料夾
mkdir -p "$HOME/Projects"
if [ ! -d "$PROJ" ]; then
    echo "📥 下載專案..."
    git clone https://github.com/hagridwu30/whisper-voice-input.git "$PROJ"
else
    echo "📥 更新專案..."
    git -C "$PROJ" pull
fi

cd "$PROJ"

# 2. 檢查 Homebrew
if ! command -v brew &>/dev/null; then
    echo "🍺 安裝 Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

# 3. 安裝 portaudio (pyaudio 需要)
echo "📦 安裝系統套件..."
brew install portaudio

# 4. 建立 venv
echo "🐍 建立 Python 虛擬環境..."
python3 -m venv venv
source venv/bin/activate

# 5. 安裝 Python 套件
echo "📦 安裝 Python 套件..."
pip install --upgrade pip -q
pip install groq opencc-python-reimplemented pyaudio pynput \
    pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices -q

# 6. 設定 GROQ_API_KEY
echo ""
if [ -z "$GROQ_API_KEY" ]; then
    echo "🔑 請輸入你的 Groq API Key（gsk_...）："
    read -r api_key
    echo "export GROQ_API_KEY=\"$api_key\"" >> ~/.zshrc
    export GROQ_API_KEY="$api_key"
    echo "✅ API Key 已儲存到 ~/.zshrc"
else
    echo "✅ 已偵測到 GROQ_API_KEY"
fi

# 7. 建立 .app
echo "🖥 建立 VoiceInput.app..."
mkdir -p "$PROJ/VoiceInput.app/Contents/MacOS"
mkdir -p "$PROJ/VoiceInput.app/Contents/Resources"

cat > "$PROJ/VoiceInput.app/Contents/MacOS/VoiceInput" << LAUNCHER
#!/bin/bash
source ~/.zshrc 2>/dev/null || source ~/.zprofile 2>/dev/null || true
cd "$PROJ"
source "$PROJ/venv/bin/activate"
exec python "$PROJ/voice_input.py"
LAUNCHER

cat > "$PROJ/VoiceInput.app/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>VoiceInput</string>
    <key>CFBundleDisplayName</key>
    <string>VoiceInput</string>
    <key>CFBundleIdentifier</key>
    <string>com.tedstudio.voiceinput</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleExecutable</key>
    <string>VoiceInput</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>VoiceInput 需要麥克風權限來錄製語音</string>
    <key>NSAppleEventsUsageDescription</key>
    <string>VoiceInput 需要此權限來輸入文字</string>
</dict>
</plist>
PLIST

chmod +x "$PROJ/VoiceInput.app/Contents/MacOS/VoiceInput"

# 8. 複製到 ~/Applications
mkdir -p "$HOME/Applications"
cp -r "$PROJ/VoiceInput.app" "$HOME/Applications/"
echo "✅ VoiceInput.app 已安裝到 ~/Applications"

echo ""
echo "🎉 安裝完成！"
echo ""
echo "接下來需要手動開啟兩個系統權限："
echo "  系統設定 → 隱私權與安全性 → 麥克風 → 開啟 Python"
echo "  系統設定 → 隱私權與安全性 → 輔助使用 → 開啟 Python"
echo ""
echo "▶ 啟動方式：雙擊 ~/Applications/VoiceInput.app"
echo "  或執行：cd $PROJ && ./run.sh"
echo ""
echo "🎙 使用：按住 Right Option 錄音，放開後自動貼入文字"
