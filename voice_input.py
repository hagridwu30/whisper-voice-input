#!/usr/bin/env python3
"""
語音輸入 App - 按住 Right Option 錄音，放開後辨識並注入文字
支援繁體中文 + 英文混合輸入
"""

import io
import os
import sys
import time
import queue
import threading
import tempfile
import wave
import subprocess
import pyaudio
import opencc
from groq import Groq
from pynput import keyboard

import config

# ── macOS 原生 UI (浮動視窗) ──────────────────────────────────────────────────
import objc
from AppKit import (
    NSApplication, NSWindow, NSView, NSTextField, NSColor, NSFont,
    NSMakeRect, NSBorderlessWindowMask, NSFloatingWindowLevel,
    NSBackingStoreBuffered, NSTimer, NSRunLoop, NSDefaultRunLoopMode,
    NSStatusBar, NSMenu, NSMenuItem, NSImage, NSVariableStatusItemLength,
)
from Foundation import NSObject, NSThread

# ── 全域狀態 ─────────────────────────────────────────────────────────────────
status_item = None  # 選單列圖示
is_recording = False
audio_frames = []
pa = None
stream = None
status_window = None
status_label = None
converter = opencc.OpenCC("s2twp")  # 簡體 → 繁體台灣

client = Groq(api_key=config.GROQ_API_KEY)


# ── 浮動視窗 ──────────────────────────────────────────────────────────────────
def create_status_window():
    global status_window, status_label

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # NSApplicationActivationPolicyAccessory (不在 Dock 顯示)

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 220, 44),
        NSBorderlessWindowMask,
        NSBackingStoreBuffered,
        False,
    )
    win.setBackgroundColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.1, 0.1, 0.85))
    win.setOpaque_(False)
    win.setLevel_(NSFloatingWindowLevel)
    win.setAlphaValue_(0.0)  # 初始隱藏
    win.setCollectionBehavior_(1 << 3)  # NSWindowCollectionBehaviorCanJoinAllSpaces

    label = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 220, 44))
    label.setStringValue_("🎙 錄音中...")
    label.setAlignment_(1)  # center
    label.setFont_(NSFont.systemFontOfSize_(15))
    label.setTextColor_(NSColor.whiteColor())
    label.setBackgroundColor_(NSColor.clearColor())
    label.setBezeled_(False)
    label.setEditable_(False)
    label.setSelectable_(False)

    win.contentView().addSubview_(label)

    # 置於螢幕底部中央
    screen = win.screen()
    if screen:
        sf = screen.frame()
        x = (sf.size.width - 220) / 2
        y = config.WINDOW_Y_OFFSET
        win.setFrameOrigin_((x, y))

    status_window = win
    status_label = label


def show_status(text):
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
    """在主執行緒執行 UI 更新"""
    if threading.current_thread() is threading.main_thread():
        fn()
    else:
        NSThread.performSelectorOnMainThread_withObject_waitUntilDone_(
            objc.selector(lambda self: fn(), signature=b"v@:"),
            None, False
        )


# ── 錄音 ─────────────────────────────────────────────────────────────────────
def start_recording():
    global is_recording, audio_frames, pa, stream
    if is_recording:
        return
    is_recording = True
    audio_frames = []

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paInt16,
        channels=config.CHANNELS,
        rate=config.SAMPLE_RATE,
        input=True,
        frames_per_buffer=config.CHUNK_SIZE,
    )
    show_status("🎙 錄音中...")

    def record_loop():
        while is_recording:
            data = stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
            audio_frames.append(data)

    threading.Thread(target=record_loop, daemon=True).start()


def stop_recording_and_transcribe():
    global is_recording, pa, stream
    if not is_recording:
        return
    is_recording = False
    time.sleep(0.05)  # 等最後一個 chunk

    if stream:
        stream.stop_stream()
        stream.close()
    if pa:
        pa.terminate()

    if not audio_frames:
        hide_status()
        return

    show_status("⏳ 辨識中...")
    threading.Thread(target=_transcribe_and_inject, daemon=True).start()


# ── 辨識 + 注入 ───────────────────────────────────────────────────────────────
def _transcribe_and_inject():
    try:
        # 組成 WAV bytes
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(config.CHANNELS)
            wf.setsampwidth(2)  # paInt16 = 2 bytes
            wf.setframerate(config.SAMPLE_RATE)
            wf.writeframes(b"".join(audio_frames))
        buf.seek(0)
        buf.name = "audio.wav"  # Groq 需要副檔名

        # 呼叫 Groq Whisper
        result = client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=buf,
            language=config.LANGUAGE,
            prompt=config.INITIAL_PROMPT,
            response_format="text",
        )

        text = result.strip() if isinstance(result, str) else result.text.strip()

        if not text:
            hide_status()
            return

        # 過濾 Whisper 沒收到聲音時回傳 prompt 內容的情況
        JUNK_PHRASES = ["請使用繁體中文", "不要使用簡體中文", "常見術語", "以下是繁體中文"]
        if any(phrase in text for phrase in JUNK_PHRASES):
            hide_status()
            return

        # 簡體 → 繁體轉換
        text = converter.convert(text)

        # 注入文字
        show_status(f"✅ {text[:20]}{'...' if len(text) > 20 else ''}")
        _inject_text(text)
        time.sleep(0.8)
        hide_status()

    except Exception as e:
        show_status(f"❌ 錯誤: {str(e)[:30]}")
        time.sleep(2)
        hide_status()


def _inject_text(text):
    """把文字存到剪貼簿，Cmd+V 貼上，完成後還原原本剪貼簿內容"""
    # 先備份原本剪貼簿
    prev = subprocess.run(["pbpaste"], capture_output=True).stdout

    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    time.sleep(0.1)

    kb = keyboard.Controller()
    with kb.pressed(keyboard.Key.cmd):
        kb.tap("v")
    time.sleep(0.15)

    # 還原原本剪貼簿
    if prev:
        subprocess.run(["pbcopy"], input=prev, check=True)


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
    if not config.GROQ_API_KEY:
        print("❌ 找不到 GROQ_API_KEY，請執行：")
        print('   export GROQ_API_KEY="gsk_..."')
        sys.exit(1)

    print("✅ 語音輸入已啟動")
    print(f"   按住 Right Option 錄音，放開後自動辨識並貼入文字")
    print(f"   Ctrl+C 結束")

    # 建立 NSApplication (必須在主執行緒)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)
    create_status_window()

    # ── 選單列 Quit ──
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

    # 背景執行鍵盤監聽
    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.start()

    # 啟動 macOS run loop（讓 UI 可以運作）
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        print("\n👋 已結束")


if __name__ == "__main__":
    main()
