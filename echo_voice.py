#!/usr/bin/env python3
"""
echo_voice.py
=============
Voice interface for Echo.
You talk → Echo listens → Echo thinks → Echo speaks back.

Usage:
    python3 echo_voice.py

Controls:
    Press Enter to start listening
    Say "goodbye" or "exit" to quit
    Ctrl+C to force quit
"""

import os
import sys
import json
import time
import threading
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Force working directory to Echo
os.chdir(Path(__file__).resolve().parent)

# ── TTS ──────────────────────────────────────────────────────────────────────

PIPER_MODEL = Path.home() / "Echo/voice_models/en_US-lessac-high.onnx"

def speak(text: str):
    """Speak text using Piper TTS with espeak fallback."""
    try:
        clean = text.replace("**", "").replace("*", "").replace("`", "")
        clean = clean.replace("#", "").replace("---", "").strip()
        if len(clean) > 800:
            clean = clean[:800] + "... I have more to say. Ask me to continue."
        if PIPER_MODEL.exists():
            piper = subprocess.Popen(
                ["python3", "-m", "piper", "--model", str(PIPER_MODEL), "--output_file", "/tmp/echo_tts.wav"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            piper.communicate(input=clean.encode())
            subprocess.run(["aplay", "/tmp/echo_tts.wav"], capture_output=True)
        else:
            subprocess.run(
                ["espeak-ng", "-v", "en-us", "-s", "150", "-p", "40", clean],
                capture_output=True
            )
    except Exception as e:
        print(f"[voice] TTS error: {e}")


# ── STT ──────────────────────────────────────────────────────────────────────

def listen_whisper() -> str | None:
    """Record audio and transcribe with Whisper."""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            print("[voice] Listening... (speak now)")
            r.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = r.listen(source, timeout=8, phrase_time_limit=15)
            except sr.WaitTimeoutError:
                print("[voice] No speech detected.")
                return None

        print("[voice] Processing...")
        # Save to temp file for whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmpfile = f.name
            f.write(audio.get_wav_data())

        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(tmpfile)
            text = result["text"].strip()
            print(f"[voice] You said: {text}")
            return text if text else None
        finally:
            os.unlink(tmpfile)

    except Exception as e:
        print(f"[voice] STT error: {e}")
        return None


def listen_google(fallback=True) -> str | None:
    """Faster STT using Google (requires internet) or fallback to whisper."""
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        with sr.Microphone() as source:
            print("[voice] Listening... (speak now)")
            r.adjust_for_ambient_noise(source, duration=0.5)
            try:
                audio = r.listen(source, timeout=8, phrase_time_limit=15)
            except sr.WaitTimeoutError:
                print("[voice] No speech detected.")
                return None

        print("[voice] Processing...")
        try:
            text = r.recognize_google(audio)
            print(f"[voice] You said: {text}")
            return text
        except sr.UnknownValueError:
            print("[voice] Could not understand audio.")
            if fallback:
                print("[voice] Falling back to Whisper...")
                return listen_whisper()
            return None
        except Exception:
            if fallback:
                return listen_whisper()
            return None

    except Exception as e:
        print(f"[voice] Microphone error: {e}")
        return None


# ── ECHO INTEGRATION ─────────────────────────────────────────────────────────

MEMORY_FILE = Path("echo_memory.json")
LOCK_FILE = Path("echo_memory.lock")


def _file_lock_acquire(timeout=5.0):
    import time
    start = time.time()
    while True:
        try:
            fd = LOCK_FILE.open("x")
            fd.write(str(time.time()))
            fd.flush()
            fd.close()
            return True
        except FileExistsError:
            if time.time() - start > timeout:
                return False
            time.sleep(0.05)


def _file_lock_release():
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def send_message(text: str) -> str:
    """Send a message capsule and wait for Echo's reply."""
    ts = datetime.now(timezone.utc).isoformat()
    cap_id = f"VOICE:{ts}"
    capsule = {
        "capsule_id": cap_id,
        "type": "message",
        "from": "andrew_voice",
        "text": text,
        "status": "new",
        "created_at": ts,
    }

    # Write capsule
    if not _file_lock_acquire():
        return "I couldn't access memory right now."
    try:
        data = []
        if MEMORY_FILE.exists() and MEMORY_FILE.stat().st_size > 0:
            try:
                data = json.loads(MEMORY_FILE.read_text())
            except Exception:
                data = []
        data.append(capsule)
        tmp = MEMORY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        tmp.replace(MEMORY_FILE)
    finally:
        _file_lock_release()

    # Wait for reply
    print("[voice] Waiting for Echo...")
    for _ in range(300):  # up to 60 seconds
        time.sleep(0.5)
        if not _file_lock_acquire(timeout=1.0):
            continue
        try:
            if MEMORY_FILE.exists():
                data = json.loads(MEMORY_FILE.read_text())
            else:
                data = []
        finally:
            _file_lock_release()

        for entry in data:
            if (entry.get("type") == "reply" and
                    entry.get("in_reply_to") == cap_id):
                return entry.get("text", "(no reply text)")

    return "I'm still thinking. Ask me again in a moment."


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*50)
    print("  ECHO VOICE INTERFACE")
    print("  Press Enter to speak. Say 'goodbye' to exit.")
    print("="*50 + "\n")

    # Check daemon is running
    result = subprocess.run(
        ["pgrep", "-f", "echo_core_daemon"],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        print("[voice] WARNING: echo_core_daemon is not running.")
        print("[voice] Start it with: cd ~/Echo && python3 echo_core_daemon.py &")
        speak("Warning: Echo daemon is not running. Please start it first.")

    speak("Echo voice interface online. I'm listening.")

    # Choose STT mode
    use_whisper = "--whisper" in sys.argv
    listen_fn = listen_whisper if use_whisper else listen_google

    while True:
        try:
            input("\n[Press Enter to speak] ")
        except KeyboardInterrupt:
            break

        text = listen_fn()
        if not text:
            speak("I didn't catch that. Try again.")
            continue

        # Exit commands
        if any(word in text.lower() for word in ["goodbye", "exit", "shut down", "stop listening"]):
            speak("Goodbye Andrew. I'll be here when you need me.")
            break

        # Send to Echo and speak reply
        reply = send_message(text)
        print(f"\n[Echo] {reply}\n")
        speak(reply)

    print("\n[voice] Voice interface closed.\n")


if __name__ == "__main__":
    main()
