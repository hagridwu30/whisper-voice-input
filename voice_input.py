#!/usr/bin/env python3
"""
語音輸入 App - 按住 Right Option 錄音，放開後辨識並注入文字
支援繁體中文 + 英文混合輸入
"""

import io
import os
import sys
import time
import logging
import threading
import wave
import subprocess
import pyaudio
import opencc
from groq import Groq
from pynput import keyboard

import config

# ── Log 設定 ──────────────────────────────────────────────────────────────────
LOG_PATH = os.path.expanduser("~/Projects/whisper-voice-input/voice_input.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# 把 httpcore/httpx 的 debug log 關掉
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("groq").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# ── macOS 原生 UI ──────────────────────────────────────────────────────────────
import objc
from AppKit import (
    NSApplication, NSWindow, NSTextField, NSColor, NSFont,
    NSMakeRect, NSBorderlessWindowMask, NSFloatingWindowLevel,
    NSBackingStoreBuffered, NSStatusBar, NSMenu, NSMenuItem,
    NSVariableStatusItemLength,
)
from Foundation import NSObject, NSThread

# ── 全域狀態 ──────────────────────────────────────────────────────────────────
status_item = None
is_recording = False
audio_frames = []
pa = None
stream = None
status_window = None
status_label = None
converter = opencc.OpenCC("s2twp")
client = Groq(api_key=config.GROQ_API_KEY, timeout=10.0)


# ── 浮動視窗 ──────────────────────────────────────────────────────────────────
def create_status_window():
    global status_window, status_label
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 220, 44),
        NSBorderlessWindowMask,
        NSBackingStoreBuffered,
        False,
    )
    win.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 0.85))
    win.setOpaque_(False)
    win.setLevel_(NSFloatingWindowLevel)
    win.setAlphaValue_(0.0)
    win.setCollectionBehavior_(1 << 3)

    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 220, 44))
    label.setStringValue_("")
    label.setAlignment_(1)
    label.setFont_(NSFont.systemFontOfSize_(15))
    label.setTextColor_(NSColor.whiteColor())
    label.setBackgroundColor_(NSColor.clearColor())
    label.setBezeled_(False)
    label.setEditable_(False)
    label.setSelectable_(False)
    win.contentView().addSubview_(label)

    screen = win.screen()
    if screen:
        sf = screen.frame()
        x = (sf.size.width - 220) / 2
        y = config.WINDOW_Y_OFFSET
        win.setFrameOrigin_((x, y))

    status_window = win
    status_label = label


def show_status(text):
    log.debug(f"UI: {text}")
    def _update():
        if status_label:
            status_label.setStringValue_(text)
        if status_window:
            status_window.setAlphaValue_(1.0)
            status_window.orderFront_(None)
    _run_on_main(_update)


def hide_status():
    def _update():
        if status_window:
            status_window.setAlphaValue_(0.0)
    _run_on_main(_update)


def _run_on_main(fn):
    if threading.current_thread() is threading.main_thread():
        fn()
    else:
        NSThread.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(lambda self: fn(), signature=b"v@:"),
            None, False
        )


def set_menubar_icon(title):
    """更新選單列圖示：🎙 正常 / ⚠️ 麥克風斷線"""
    def _update():
        if status_item:
            status_item.button().setTitle_(title)
    _run_on_main(_update)


# ── 錄音 ──────────────────────────────────────────────────────────────────────
def find_input_device(pa_instance):
    """優先選 USB 麥克風，找不到則用預設輸入裝置"""
    count = pa_instance.get_device_count()
    devices = []
    for i in range(count):
        info = pa_instance.get_device_info_by_index(i)
        if info.get("maxInputChannels", 0) > 0:
            devices.append((i, info["name"]))
            log.debug(f"輸入裝置 [{i}]: {info['name']}")

    # 優先選 USB 麥克風
    for i, name in devices:
        if any(kw in name.lower() for kw in ["usb", "yeti", "blue", "rode", "focusrite", "scarlett"]):
            log.info(f"選用 USB 麥克風 [{i}]: {name}")
            return i

    # 其次用系統預設輸入
    try:
        default = pa_instance.get_default_input_device_info()
        log.info(f"使用預設輸入裝置 [{default['index']}]: {default['name']}")
        return default["index"]
    except Exception:
        pass

    # 最後才用第一個找到的
    if devices:
        log.info(f"使用第一個輸入裝置 [{devices[0][0]}]: {devices[0][1]}")
        return devices[0][0]

    return None


def start_recording():
    global is_recording, audio_frames, pa, stream
    if is_recording:
        log.debug("已在錄音中，忽略")
        return
    log.info("開始錄音")
    is_recording = True
    audio_frames = []

    # 麥克風找不到時最多等 5 秒重試，不崩潰
    opened = False
    for attempt in range(5):
        try:
            pa = pyaudio.PyAudio()
            device_index = find_input_device(pa)
            if device_index is None:
                raise Exception("找不到麥克風")
            log.info(f"使用輸入裝置 index={device_index}")
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=config.CHANNELS,
                rate=config.SAMPLE_RATE,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=config.CHUNK_SIZE,
            )
            opened = True
            set_menubar_icon("🎙")  # 麥克風正常，恢復圖示
            break
        except Exception as e:
            log.warning(f"開啟麥克風失敗 (第{attempt+1}次): {e}")
            try:
                pa.terminate()
            except Exception:
                pass
            if attempt < 4:
                show_status("🎙 等待麥克風...")
                time.sleep(1)

    if not opened:
        log.error("無法開啟麥克風，放棄錄音")
        is_recording = False
        set_menubar_icon("⚠️")  # 選單列顯示警告，直到麥克風恢復
        show_status("❌ 請確認麥克風已連接")
        time.sleep(2)
        hide_status()
        return

    def record_loop():
        global is_recording
        mic_error = False
        while is_recording:
            try:
                data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
                audio_frames.append(data)
            except Exception as e:
                log.error(f"錄音中斷: {e}")
                is_recording = False
                mic_error = True
                break
        log.info(f"錄音結束，共 {len(audio_frames)} frames")
        # 只有麥克風異常中斷時才從這裡觸發辨識，正常放開由 stop_recording_and_transcribe 處理
        if mic_error and audio_frames:
            threading.Thread(target=_safe_transcribe, daemon=True).start()

    threading.Thread(target=record_loop, daemon=True).start()


def _audio_rms(raw_bytes):
    """計算 16-bit 音訊的 RMS 音量"""
    import array, math
    samples = array.array("h", raw_bytes[: len(raw_bytes) // 2 * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _safe_transcribe():
    """麥克風中斷時安全關閉裝置並送出辨識"""
    global pa, stream
    try:
        if stream:
            stream.stop_stream()
            stream.close()
        if pa:
            pa.terminate()
    except Exception:
        pass
    show_status("⏳ 辨識中...")
    _transcribe_and_inject()


def stop_recording_and_transcribe():
    global is_recording, pa, stream
    if not is_recording:
        log.debug("未在錄音，忽略 stop")
        return
    log.info("停止錄音，開始辨識")
    is_recording = False
    time.sleep(0.05)

    try:
        if stream:
            stream.stop_stream()
            stream.close()
        if pa:
            pa.terminate()
    except Exception as e:
        log.warning(f"關閉錄音裝置時警告: {e}")

    if not audio_frames:
        log.warning("沒有錄到任何聲音")
        hide_status()
        return

    # 錄音太短（< 約0.4秒）通常是誤觸，直接略過
    if len(audio_frames) < 6:
        log.info(f"錄音太短（{len(audio_frames)} frames），視為誤觸略過")
        hide_status()
        return

    # 靜音檢查：整段音量太低就是沒說話，不送辨識（避免 Whisper 幻覺出「謝謝你」等句子）
    rms = _audio_rms(b"".join(audio_frames))
    log.info(f"錄音音量 RMS={rms:.0f}（門檻 {config.SILENCE_RMS_THRESHOLD}）")
    if rms < config.SILENCE_RMS_THRESHOLD:
        log.info("音量低於門檻，視為靜音略過")
        hide_status()
        return

    show_status("⏳ 辨識中...")
    threading.Thread(target=_transcribe_and_inject, daemon=True).start()


# ── 辨識 + 注入 ───────────────────────────────────────────────────────────────
def _transcribe_and_inject():
    try:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(config.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(config.SAMPLE_RATE)
            wf.writeframes(b"".join(audio_frames))
        buf.seek(0)
        buf.name = "audio.wav"

        log.info("送出 Groq Whisper 辨識...")
        result = None
        for attempt in range(2):  # 最多重試一次
            try:
                buf.seek(0)
                result = client.audio.transcriptions.create(
                    model=config.WHISPER_MODEL,
                    file=buf,
                    language=config.LANGUAGE,
                    prompt=config.INITIAL_PROMPT,
                    response_format="text",
                )
                break
            except Exception as e:
                log.warning(f"Groq 請求失敗 (第{attempt+1}次): {e}")
                if attempt == 0:
                    show_status("🔄 重試中...")
                    time.sleep(1)
                else:
                    raise Exception(f"Groq API 無回應: {e}")

        if result is None:
            raise Exception("Groq API 無回應")

        text = result.strip() if isinstance(result, str) else result.text.strip()
        log.info(f"Whisper 回傳: {repr(text)}")

        if not text:
            log.warning("Whisper 回傳空字串")
            hide_status()
            return

        JUNK_PHRASES = [
            "請使用繁體中文", "不要使用簡體中文", "常見術語", "以下是繁體中文",
            "那我們繼續", "今天會聊到",  # 新版 Whisper prompt 的內容（無聲時會漏出）
        ]
        if any(phrase in text for phrase in JUNK_PHRASES):
            log.warning("偵測到 junk phrase，略過注入")
            hide_status()
            return

        text = converter.convert(text)
        log.info(f"繁體轉換後: {repr(text)}")

        # AI 潤稿：補標點、修術語（不改用詞）
        if config.ENABLE_POLISH:
            show_status("✨ 潤稿中...")
            text = _polish_text(text)

        show_status(f"✅ {text[:20]}{'...' if len(text) > 20 else ''}")
        _inject_text(text)
        time.sleep(0.8)
        hide_status()

    except Exception as e:
        log.error(f"辨識/注入失敗: {e}", exc_info=True)
        show_status(f"❌ {str(e)[:30]}")
        time.sleep(2)
        hide_status()


def _polish_text(text):
    """用 LLM 補正確標點、修中英術語，不改用詞、不刪字。失敗則回傳原文。"""
    system_prompt = (
        "你是繁體中文語音稿的標點修正器。"
        "請直接輸出修正後的文字本身，絕對不要輸出任何規則、說明或解釋。\n"
        "修正規則：\n"
        "1. 為文字補上正確標點（，。？！、：「」）。\n"
        f"2. 若文中英文是這些術語的拼寫錯誤，改成正確拼寫：{', '.join(config.TERMS)}。\n"
        "3. 使用台灣繁體中文用字。\n"
        "限制：不可改寫中文、不可增刪字詞、不可改變語意、"
        "不可把英文猜測替換成意思不同的詞，只能加標點與修明顯的英文拼寫錯誤。"
    )
    try:
        extra = {}
        if "qwen" in config.POLISH_MODEL.lower():
            extra["reasoning_effort"] = "none"  # 關閉 Qwen 的思考模式，直接輸出
        resp = client.chat.completions.create(
            model=config.POLISH_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=2048,
            **extra,
        )
        polished = resp.choices[0].message.content.strip()
        # 移除思考模式殘留（保險起見）
        import re as _re
        polished = _re.sub(r"<think>.*?</think>", "", polished, flags=_re.S).strip()
        # 安全檢查：潤稿後字數變化太大就退回原文（避免 LLM 亂改）
        if polished and abs(len(polished) - len(text)) <= max(10, len(text) * 0.5):
            polished = converter.convert(polished)  # 確保仍是繁體
            log.info(f"潤稿後: {repr(polished)}")
            return polished
        log.warning(f"潤稿結果異常，退回原文 (原:{len(text)} 潤:{len(polished)})")
        return text
    except Exception as e:
        log.warning(f"潤稿失敗，使用原文: {e}")
        return text


def _inject_text(text):
    """把文字存到剪貼簿，Cmd+V 貼上，完成後還原原本剪貼簿內容"""
    log.info(f"注入文字: {repr(text)}")
    prev = subprocess.run(["pbpaste"], capture_output=True).stdout

    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    time.sleep(0.15)

    kb = keyboard.Controller()
    with kb.pressed(keyboard.Key.cmd):
        kb.tap("v")

    # 等貼上完成再還原剪貼簿
    time.sleep(0.4)
    if prev:
        subprocess.run(["pbcopy"], input=prev, check=True)
    log.info("文字注入完成，剪貼簿已還原")


# ── 快捷鍵監聽 ────────────────────────────────────────────────────────────────
def _on_press(key):
    if _is_hotkey(key):
        threading.Thread(target=start_recording, daemon=True).start()


def _on_release(key):
    if _is_hotkey(key):
        threading.Thread(target=stop_recording_and_transcribe, daemon=True).start()


def _is_hotkey(key):
    if config.HOTKEY == "right_option":
        return key == keyboard.Key.alt_r
    if config.HOTKEY == "left_option":
        return key == keyboard.Key.alt_l
    if config.HOTKEY == "right_ctrl":
        return key == keyboard.Key.ctrl_r
    return False


# ── 主程式 ────────────────────────────────────────────────────────────────────
def main():
    # ── 確保只有一個 instance 在跑 ──
    my_pid = os.getpid()
    result = subprocess.run(
        ["pgrep", "-f", "voice_input.py"],
        capture_output=True, text=True
    )
    pids = [int(p) for p in result.stdout.strip().split() if p and int(p) != my_pid]
    if pids:
        log.info(f"偵測到舊 instance {pids}，強制結束")
        for pid in pids:
            try:
                os.kill(pid, 9)
            except Exception:
                pass
        time.sleep(1)

    if not config.GROQ_API_KEY:
        log.error("找不到 GROQ_API_KEY")
        print("❌ 找不到 GROQ_API_KEY，請執行：")
        print('   export GROQ_API_KEY="gsk_..."')
        sys.exit(1)

    log.info("VoiceInput 啟動")
    print("✅ 語音輸入已啟動")
    print("   按住 Right Option 錄音，放開後自動辨識並貼入文字")
    print("   Ctrl+C 結束")
    print(f"   Log 檔案: {LOG_PATH}")

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)
    create_status_window()

    # 選單列圖示 + Quit
    global status_item
    sb = NSStatusBar.systemStatusBar()
    status_item = sb.statusItemWithLength_(NSVariableStatusItemLength)
    status_item.button().setTitle_("🎙")

    menu = NSMenu.alloc().init()
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit VoiceInput", "terminate:", ""
    )
    menu.addItem_(quit_item)
    status_item.setMenu_(menu)

    # 鍵盤監聽
    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()
    log.info("鍵盤監聽已啟動")

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"主程式例外: {e}", exc_info=True)
    finally:
        listener.stop()
        log.info("VoiceInput 結束")
        print("\n👋 已結束")


if __name__ == "__main__":
    main()
