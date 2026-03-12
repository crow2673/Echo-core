#!/usr/bin/env python3
import os
import speech_recognition as sr
import pyaudio
from vosk import Model, KaldiRecognizer
import json
import subprocess
import ollama
import pyttsx3  # TTS
import sys
import time

model_path = os.path.expanduser("~/vosk-model/vosk-model-small-en-us-0.15")
model = Model(model_path)
rec = KaldiRecognizer(model, 16000)

r = sr.Recognizer()
try:
    mic = sr.Microphone()
    print("🔴 JARVIS LISTENING... Say 'Jarvis' to wake. (Ctrl+C quit)")
    with mic as source:
        r.adjust_for_ambient_noise(source, duration=1)
except Exception as e:
    print(f"Mic init err: {e}. Check pavucontrol ALC1220.")
    sys.exit(1)

engine = pyttsx3.init()  # TTS ready

while True:
    try:
        with mic as source:
            audio = r.listen(source, timeout=2, phrase_time_limit=6)
        if rec.AcceptWaveform(audio.get_wav_data()):
            result = json.loads(rec.Result())
            text = result.get('text', '').lower()
            if 'jarvis' in text:
                print(f"🟢 JARVIS HEARD: '{text}' → Qwen...")
                resp = ollama.chat(model='qwen2.5:7b', messages=[{'role': 'user', 'content': text}])
                action = resp['message']['content']
                print(f"🤖 JARVIS ACT: {action}")
                # TTS speak
                engine.say(action)
                engine.runAndWait()
                # Trade hook
                if any(word in text for word in ['trade', 'kucoin', 'buy', 'sell']):
                    subprocess.run(['python3', 'echo_simple_agent.py', text], cwd=os.path.dirname(__file__))
    except sr.WaitTimeoutError:
        pass  # Silent ok
    except sr.UnknownValueError:
        pass  # No speech
    except sr.RequestError as e:
        print(f"Mic err: {e}")
        time.sleep(5)
    except KeyboardInterrupt:
        print("JARVIS OFF.")
        sys.exit(0)
