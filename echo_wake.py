#!/usr/bin/env python3
"""
echo_wake.py
Always-on wake word listener for Echo.
Listens continuously for "Echo" then activates full voice session.
Run as: python3 echo_wake.py
"""
import subprocess
import sys
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import speech_recognition as sr
from echo_voice import speak, send_message

WAKE_WORDS = ["echo", "hey echo", "okay echo"]
import queue
reply_queue = queue.Queue()
import queue
reply_queue = queue.Queue()
MIC_INDEX = 4  # ALC1220 Analog

def listen_for_wake(recognizer, source):
    try:
        audio = recognizer.listen(source, timeout=3, phrase_time_limit=4)
        text = recognizer.recognize_google(audio).lower()
        print(f"[wake] heard: {text}")
        if any(w in text for w in ["goodbye", "shut down", "exit", "stop listening"]):
            speak("Goodbye Andrew.")
            raise SystemExit(0)
        return any(w in text for w in WAKE_WORDS)
    except sr.WaitTimeoutError:
        return False
    except sr.UnknownValueError:
        return False
    except Exception as e:
        print(f"[wake] error: {e}")
        return False

def handle_command(recognizer, source):
    speak("Yes?")
    try:
        audio = recognizer.listen(source, timeout=8, phrase_time_limit=20)
        text = recognizer.recognize_google(audio)
        if not text:
            speak("I didn't catch that.")
            return
        print(f"[command] {text}")
        import threading
        def send_and_queue(msg):
            reply = send_message(msg)
            if reply and "still thinking" not in reply:
                reply_queue.put(reply)
            else:
                reply_queue.put("I finished processing but had no reply.")
        threading.Thread(target=send_and_queue, args=(text,), daemon=True).start()
    except sr.WaitTimeoutError:
        speak("I didn't hear anything.")
    except sr.UnknownValueError:
        speak("I didn't catch that.")
    except Exception as e:
        print(f"[command] error: {e}")
        speak("Something went wrong.")

def run():
    print("[Echo] Always-on wake word listener starting...")
    print(f"[Echo] Say 'Echo' to activate. Using mic index {MIC_INDEX}.")
    speak("Echo is listening.")

    r = sr.Recognizer()
    r.energy_threshold = 300
    r.dynamic_energy_threshold = True
    r.pause_threshold = 0.8

    with sr.Microphone(device_index=MIC_INDEX) as source:
        r.adjust_for_ambient_noise(source, duration=2)
        print(f"[Echo] Ambient noise adjusted. Energy threshold: {r.energy_threshold:.0f}")
        print("[Echo] Listening for wake word...")
        while True:
            # Speak any queued replies first
            try:
                reply = reply_queue.get_nowait()
                speak(reply)
            except queue.Empty:
                pass

            try:
                reply = reply_queue.get_nowait()
                speak(reply)
            except queue.Empty:
                pass
            if listen_for_wake(r, source):
                print("[Echo] Wake word detected!")
                handle_command(r, source)
                print("[Echo] Back to listening...")

if __name__ == "__main__":
    run()
