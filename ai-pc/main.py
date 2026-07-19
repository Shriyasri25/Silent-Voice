"""
Silent Voice — AI PC brain

Responsibilities:
  1. Read gesture labels from Arduino over serial.
  2. Receive expression labels from the mobile device over HTTP (Flask).
  3. Fuse gesture + expression -> look up a phrase.
  4. Speak the phrase aloud (offline TTS via pyttsx3).
  5. Log every session event so cloud_sync.py can push it to Cloud AI 100.
  6. Print a live terminal readout (gesture, expression, phrase, latency).

Run:
  pip install -r requirements.txt
  python main.py

Before running, set SERIAL_PORT below to match your Arduino
(Windows: "COM3" etc. | macOS/Linux: "/dev/tty.usbmodemXXXX" or "/dev/ttyACM0").
"""

import json
import threading
import time

import serial
from flask import Flask, request

from speech import get_engine, get_speech_status

# ---- Config ---------------------------------------------------------------

SERIAL_PORT = "COM3"       # <-- change this to your Arduino's port
BAUD_RATE = 9600
FLASK_PORT = 5000

# ---- Setup ------------------------------------------------------------------

with open("phrases.json") as f:
    PHRASES = json.load(f)

# Speech engine is initialised once here; it reads .env automatically.
_speech = get_engine()

app = Flask(__name__)

current_expression = "NEUTRAL"
session_log = []  # each entry: {gesture, expression, phrase, timestamp}


# ---- Mobile -> AI PC endpoint ------------------------------------------------

@app.route("/expression", methods=["POST"])
def update_expression():
    global current_expression
    current_expression = request.json.get("expression", "NEUTRAL")
    return "OK"


def run_flask():
    app.run(port=FLASK_PORT, host="0.0.0.0")


# ---- Core loop ----------------------------------------------------------------

def speak(phrase: str):
    # Delegates to SpeechEngine — tries Sarvam AI, auto-falls back to pyttsx3.
    _speech.speak(phrase)


def resolve_phrase(gesture_code: str, expression: str) -> str:
    # Direct lookup: gesture_code is one of "000".."111" from the glove.
    # expression is logged alongside for the demo/dashboard but doesn't
    # change which phrase is spoken — the 8-gesture table is fixed.
    return PHRASES.get(gesture_code, "I need help")


def main():
    print(f"[Silent Voice] Opening serial port {SERIAL_PORT} @ {BAUD_RATE}...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # allow Arduino to reset after serial connect

    print(f"[Silent Voice] Flask listening on :{FLASK_PORT} for mobile expression updates")
    threading.Thread(target=run_flask, daemon=True).start()

    print("[Silent Voice] Ready. Waiting for gestures...\n")
    last_gesture = None

    while True:
        if ser.in_waiting:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw or len(raw) != 3 or any(c not in "01" for c in raw):
                continue  # ignore malformed lines (noise, partial reads)

            gesture = raw  # e.g. "000", "101", "111"
            if gesture == last_gesture:
                continue  # avoid repeating the same phrase every debounce tick
            last_gesture = gesture

            t0 = time.time()
            phrase = resolve_phrase(gesture, current_expression)
            speak(phrase)
            latency_ms = int((time.time() - t0) * 1000)

            entry = {
                "gesture": gesture,
                "expression": current_expression,
                "phrase": phrase,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
                "speech_status": get_speech_status(),
            }
            session_log.append(entry)

            print(
                f"gesture={gesture:<6} expression={current_expression:<8} "
                f"phrase='{phrase}'  latency={latency_ms}ms  "
                f"(session total: {len(session_log)})"
            )


if __name__ == "__main__":
    main()
