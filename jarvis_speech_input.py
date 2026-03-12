#!/usr/bin/env python3
import os
import speech_recognition as sr
import pyaudio  # pip install SpeechRecognition pyaudio vosk
from vosk import Model, KaldiRecognizer
import json
import subprocess
import ollama
import sys

# Download vosk-model-small-en-us-0.15: wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && unzip
model = Model(os.path.expanduser("~/vosk-model/vosk-model-small-en-us-0.15"))  # Place in ~/vosk-model
rec = KaldiRecognizer(model, 16000)

r = sr.Recognizer()
mic = sr.Microphone()

print("🔴 JARVIS LISTENING... Say 'Jarvis' to wake.")
with mic as source:
    r.adjust_for_ambient_noise(source)

while True:
    try:
        with mic as source:
            audio = r.listen(source, timeout=1, phrase_time_limit=5)
        if rec.AcceptWaveform(audio.get_wav_data()):
            result = json.loads(rec.Result())
            text = result.get('text', '').lower()
            if 'jarvis' in text:
                print(f"🟢 JARVIS: '{text}' → Processing...")
                # Ollama Qwen act
                resp = ollama.chat(model='qwen2.5:7b', messages=[{'role': 'user', 'content': text}])
                action = resp['message']['content']
                print(f"JARVIS ACT: {action}")
                # TTS hook (call your jarvis_voice.py)
                subprocess.run(['python3', 'jarvis_voice.py', action])
                # CCXT TRADE HOOK: if 'trade' in text → echo_simple_agent.py
                if 'trade' in text or 'kucoin' in text:
                    subprocess.run(['python3', 'echo_simple_agent.py', text])
    except sr.WaitTimeoutError:
        pass
    except KeyboardInterrupt:
        sys.exit(0)
