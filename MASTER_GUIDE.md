# Silent Voice — MASTER GUIDE (Everything, Start to Finish)

This one document has everything: hardware wiring, all the code, and every step to
run it on your Windows laptop. Follow it top to bottom in order.

Your project folder (from what you've shown me) is at:
`C:\Users\anike\Downloads\silent-voice\silent-voice`
(it got extracted twice, so there's a nested folder — that's fine, just always use
this full path below.)

---

## PART 1 — Hardware: wire the glove

3 flex sensors, wired as voltage dividers:

```
5V ──── sensor ──┬──── Analog Pin (A0/A1/A2)
                  │
                 10kΩ resistor
                  │
                 GND
```

| Sensor | Finger  | Arduino pin |
|--------|---------|-------------|
| 1      | Index   | A0          |
| 2      | Middle  | A1          |
| 3      | Ring    | A2          |

## PART 1b — The 8 gestures this system recognizes

Bit order is always **Index, Middle, Ring** — `0` = straight, `1` = bent.

| Code | Gesture         | Voice Output                                | Category           |
|------|-----------------|-----------------------------------------------|---------------------|
| 000  | Open Hand       | "Hello"                                        | Greeting            |
| 100  | Index Bent      | "I am thirsty."                                | Daily Need          |
| 010  | Middle Bent     | "I need food."                                 | Daily Need          |
| 001  | Ring Bent       | "I need medicine."                             | Medical             |
| 110  | Index + Middle  | "Please help me."                              | Emergency           |
| 101  | Index + Ring    | "Please call the doctor."                      | Medical Emergency   |
| 011  | Middle + Ring   | "I need my wheelchair."                        | Mobility            |
| 111  | All Bent        | "Emergency! Call my caregiver immediately."    | Critical Emergency  |

---

## PART 2 — Install software (one-time only)

1. **Python** — python.org/downloads → install Python 3.11+. **Check "Add python.exe to PATH"** during install.
2. **Arduino IDE** — arduino.cc/en/software → install.

---

## PART 3 — Arduino: upload and test the glove

1. Plug in the Arduino UNO Q via USB.
2. Open Arduino IDE → **File → Open** →
   `C:\Users\anike\Downloads\silent-voice\silent-voice\arduino\glove_firmware.ino`
3. **Tools → Board** → select Arduino UNO Q.
4. **Tools → Port** → note the COM number (check **Device Manager → Ports (COM & LPT)**
   if unsure — look for "Arduino" or "USB Serial Device").
5. Click **Upload**.
6. Open **Tools → Serial Monitor**, set baud rate to **9600**.
7. Bend fingers, confirm codes `000` through `111` print correctly.
8. **Close Serial Monitor and the whole Arduino IDE window** before moving to Part 4 —
   only one program can hold the COM port at a time.

**Firmware code** (`arduino/glove_firmware.ino`) — already in your downloaded folder:

```cpp
/*
  Silent Voice — Glove Firmware (Final: 3 Flex Sensors, 8 Gestures)
  Reads 3 flex sensors on A0-A2 (Index, Middle, Ring), classifies each as
  STRAIGHT (0) or BENT (1), and sends the 3-bit code over Serial.
*/

const int PIN_INDEX  = A0;
const int PIN_MIDDLE = A1;
const int PIN_RING   = A2;

const int BEND_THRESHOLD = 650;  // calibrate this per your sensors

String lastCode = "";
unsigned long lastSendTime = 0;
const unsigned long DEBOUNCE_MS = 150;

void setup() {
  Serial.begin(9600);
}

int bitFor(int pin) {
  int val = analogRead(pin);
  return (val <= BEND_THRESHOLD) ? 1 : 0;
}

String readGestureCode() {
  int indexBit  = bitFor(PIN_INDEX);
  int middleBit = bitFor(PIN_MIDDLE);
  int ringBit   = bitFor(PIN_RING);
  String code = "";
  code += String(indexBit);
  code += String(middleBit);
  code += String(ringBit);
  return code;
}

void loop() {
  String code = readGestureCode();
  unsigned long now = millis();
  if (code != lastCode || (now - lastSendTime) > 1000) {
    Serial.println(code);
    lastCode = code;
    lastSendTime = now;
  }
  delay(DEBOUNCE_MS);
}
```

---

## PART 4 — AI PC: the brain (gesture → speech)

**Open a terminal in the right folder:**
1. In File Explorer, go to
   `C:\Users\anike\Downloads\silent-voice\silent-voice\ai-pc`
2. Click the address bar, type `cmd`, press Enter. A terminal opens already in this folder.

**Install packages (one-time):**
```
pip install -r requirements.txt
```

**Set your COM port:**
Open `main.py` in Notepad, find:
```python
SERIAL_PORT = "COM3"
```
Change `"COM3"` to your actual port from Part 3, Step 4. Save.

**Run it:**
```
python main.py
```
Expected output: `[Silent Voice] Ready. Waiting for gestures...`
Bend a finger on the glove — you should **hear the phrase spoken aloud**.
✅ **This is your MVP. If this works, you have a working demo.**

**Full code** (`ai-pc/main.py`) — already in your downloaded folder:

```python
"""
Silent Voice — AI PC brain
Reads gesture codes from Arduino, receives expression labels from mobile,
looks up the matching phrase, speaks it aloud, and logs the session.
"""

import json
import threading
import time

import pyttsx3
import serial
from flask import Flask, request

SERIAL_PORT = "COM3"       # <-- change this to your Arduino's port
BAUD_RATE = 9600
FLASK_PORT = 5000

with open("phrases.json") as f:
    PHRASES = json.load(f)

engine = pyttsx3.init()
engine.setProperty("rate", 165)

app = Flask(__name__)
current_expression = "NEUTRAL"
session_log = []


@app.route("/expression", methods=["POST"])
def update_expression():
    global current_expression
    current_expression = request.json.get("expression", "NEUTRAL")
    return "OK"


def run_flask():
    app.run(port=FLASK_PORT, host="0.0.0.0")


def speak(phrase: str):
    engine.say(phrase)
    engine.runAndWait()


def resolve_phrase(gesture_code: str, expression: str) -> str:
    return PHRASES.get(gesture_code, "I need help")


def main():
    print(f"[Silent Voice] Opening serial port {SERIAL_PORT} @ {BAUD_RATE}...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

    print(f"[Silent Voice] Flask listening on :{FLASK_PORT}")
    threading.Thread(target=run_flask, daemon=True).start()

    print("[Silent Voice] Ready. Waiting for gestures...\n")
    last_gesture = None

    while True:
        if ser.in_waiting:
            raw = ser.readline().decode(errors="ignore").strip()
            if not raw or len(raw) != 3 or any(c not in "01" for c in raw):
                continue

            gesture = raw
            if gesture == last_gesture:
                continue
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
            }
            session_log.append(entry)

            print(
                f"gesture={gesture:<6} expression={current_expression:<8} "
                f"phrase='{phrase}'  latency={latency_ms}ms  "
                f"(session total: {len(session_log)})"
            )


if __name__ == "__main__":
    main()
```

**Phrase bank** (`ai-pc/phrases.json`):
```json
{
  "000": "Hello",
  "100": "I am thirsty.",
  "010": "I need food.",
  "001": "I need medicine.",
  "110": "Please help me.",
  "101": "Please call the doctor.",
  "011": "I need my wheelchair.",
  "111": "Emergency! Call my caregiver immediately."
}
```

---

## PART 5 — Mobile/camera layer (optional polish, do this only after Part 4 works)

**Keep Part 4's terminal running.** Open a **second, new** terminal window:
1. Go to `C:\Users\anike\Downloads\silent-voice\silent-voice\mobile`
2. Click address bar → type `cmd` → Enter
3. Install:
   ```
   pip install -r requirements.txt
   ```
4. Run:
   ```
   python mobile_vision.py
   ```

A window titled **"Silent Voice — Mobile"** opens showing your webcam feed with a
live expression label (`HAPPY` / `SAD` / `NEUTRAL`) in the corner. Press **Esc** on
that window to close it cleanly.

This uses MediaPipe FaceMesh to track mouth-corner position — it sends the
expression to the AI PC for logging/context, but doesn't change which phrase is
spoken (your 8-gesture table is fixed).

---

## PART 6 — Cloud AI 100 sync (optional, do last)

1. Go to `C:\Users\anike\Downloads\silent-voice\silent-voice\cloud`
2. Open a terminal there, run:
   ```
   pip install -r requirements.txt
   ```
3. Open `cloud_sync.py` in Notepad, fill in your real `CLOUD_ENDPOINT` and `API_KEY`
   from the Qualcomm Cloud AI 100 console.
4. Run:
   ```
   python cloud_sync.py
   ```
   This pushes a sample session log and prints back the response — confirms the
   integration works before your live demo.

---

## PART 7 — Demo script (rehearse this exact order)

1. Open hand (`000`) → "Hello"
2. Bend index (`100`) → "I am thirsty."
3. Bend all fingers (`111`) → "Emergency! Call my caregiver immediately." — your strongest moment
4. Turn off Wi-Fi on all devices → gesture-to-speech still works (Arduino↔AI PC is USB, not Wi-Fi) → say out loud: *"this core pipeline runs 100% offline"*
5. Turn Wi-Fi back on, show the mobile expression window and the Cloud AI 100 terminal output
6. Let a judge try the glove themselves

---

## Troubleshooting quick reference

| Problem | Fix |
|---|---|
| `cd` says path not found | You're not in the right folder — use File Explorer address bar trick from Part 4/5, don't type long `cd` paths by hand |
| `could not open port 'COMx'` | Wrong port number, or Arduino IDE/Serial Monitor still has it open — close Arduino IDE fully, recheck Device Manager for the real port |
| No sound plays | Check laptop volume isn't muted; `pyttsx3` uses your default Windows voice — test it works outside this project first |
| Webcam window won't open | Check no other app (Zoom, Teams) is using the camera; check camera index 0 is correct for your laptop |
| `pip install` fails | Make sure Python was installed with "Add to PATH" checked; try `python -m pip install -r requirements.txt` instead |

---

## Full file checklist (everything in your downloaded folder)

```
silent-voice/
├── README.md
├── LICENSE
├── arduino/
│   └── glove_firmware.ino
├── ai-pc/
│   ├── main.py
│   ├── phrases.json
│   └── requirements.txt
├── mobile/
│   ├── mobile_vision.py
│   └── requirements.txt
└── cloud/
    ├── cloud_sync.py
    └── requirements.txt
```
