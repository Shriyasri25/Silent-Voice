# Silent Voice

Multi-device AAC (Augmentative & Alternative Communication) system built for the
Snapdragon Multiverse Hackathon. A gesture glove speaks for the user, a camera
reads their expression to refine the phrase, and a cloud service personalizes
their vocabulary over time.

**Team:** Shriya (Lead) + 4 members — add all 5 names + emails here before submission.

---

## 1. How the pieces connect

**Two versions of this architecture exist — know which one you're showing:**

| | Pitch-deck architecture (slides, PDF) | What's actually built here (this repo) |
|---|---|---|
| Arduino | STM32 MCU + QRB2210 MPU, Bridge RPC, BLE | Single Arduino UNO Q, USB serial |
| Mobile | OnePlus 15, FastVLM-0.5B on Hexagon NPU via LiteRT-LM | Any webcam device, MediaPipe FaceMesh (CPU) |
| AI PC | onnxruntime-genai on Surface Laptop NPU | Plain Python, pyttsx3 TTS (CPU) |
| Cloud | Qualcomm AI Inference Suite, model-delta push | Simple REST POST/response, local fallback rerank |
| Connectivity | BLE (glove↔hub) + Wi-Fi (mobile↔hub) | USB serial (glove↔hub) + Wi-Fi (mobile↔hub) |

**Why the gap is intentional, not a shortcut you should hide:** the pitch deck describes the
NPU-optimized, production version of Silent Voice — the thing you'd build with weeks and a
Qualcomm SDK deep-dive. What's in this repo is the same *system design* (4 devices, same data
flow, same phrase/gesture table) built with tools a beginner team can actually get working and
demo reliably in 24 hours. Judges care that your architecture is sound and your demo works live —
not that every box uses the fanciest possible runtime. If you get through the core MVP with time
to spare, the "Stretch goals" section below is the order to attempt real NPU/BLE upgrades in.

**Data flow (matches both versions):**

```
┌────────────────┐   USB serial    ┌──────────────────────┐
│  Arduino UNO Q   │ ───────────────▶ │      AI PC (main.py)   │
│  (flex sensors)  │   "000"/"111"    │  - resolves phrase      │
└────────────────┘   etc.            │  - speaks via pyttsx3   │
                                      │  - Flask :5000          │
┌────────────────┐   HTTP POST       │  - logs session          │
│  Mobile / camera │ ────────────────▶│                          │
│ (mobile_vision.py)│  {expression}    └──────────┬───────────┘
└────────────────┘                                │
                                                    │ session_log
                                                    ▼
                                       ┌──────────────────────┐
                                       │  Cloud AI 100 (cloud_sync.py) │
                                       │  personalization/reranking     │
                                       └──────────────────────┘
```

- **Arduino → AI PC:** USB cable, plain serial text lines (one gesture label per line).
- **Mobile → AI PC:** Wi-Fi, both devices on the same local network. Mobile script
  POSTs JSON to `http://<AI_PC_IP>:5000/expression`.
- **AI PC → Cloud AI 100:** HTTPS, `cloud_sync.py` pushes the accumulated
  `session_log` list and prints back whatever personalization the cloud returns.

---

## 2. Hardware wiring (Arduino UNO Q) — 3 Flex Sensors, 8 Gestures

Use flex sensors if you have them; potentiometers work identically as a substitute
for testing.

For each of the 3 sensors, wire it as a voltage divider:

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

Tape the sensors along the glove finger-by-finger so bending each finger changes
its analog reading. Open Serial Monitor at 9600 baud after uploading the firmware
to confirm you see a 3-digit code (e.g. `000`, `100`, `111`) printed as you bend
fingers — recalibrate `BEND_THRESHOLD` in `glove_firmware.ino` if your sensors'
resting values are very different (higher reading = straight, lower = bent).

### Final 8 gestures

| Code | Gesture               | Voice Output                               | Category           |
|------|------------------------|---------------------------------------------|---------------------|
| 000  | Open Hand              | "Hello"                                      | Greeting            |
| 100  | Index Bent             | "I am thirsty."                              | Daily Need          |
| 010  | Middle Bent            | "I need food."                               | Daily Need          |
| 001  | Ring Bent               | "I need medicine."                           | Medical             |
| 110  | Index + Middle          | "Please help me."                            | Emergency           |
| 101  | Index + Ring            | "Please call the doctor."                    | Medical Emergency   |
| 011  | Middle + Ring           | "I need my wheelchair."                      | Mobility            |
| 111  | All Bent                | "Emergency! Call my caregiver immediately."  | Critical Emergency  |

Bit order in the code is always **Index, Middle, Ring** — `0` = straight, `1` = bent.

---

## 3. Setup — run in this order

### Step 1 — Arduino
1. Open `arduino/glove_firmware.ino` in the Arduino IDE.
2. Select the correct board (Arduino UNO Q) and port.
3. Upload.
4. Open Serial Monitor (9600 baud) and confirm gesture labels print when you bend
   fingers. Close Serial Monitor afterward — only one program can hold the port at a time.

### Step 2 — AI PC
```bash
cd ai-pc
pip install -r requirements.txt
```
Edit `SERIAL_PORT` in `main.py` to match your Arduino's port (find it in the
Arduino IDE's Tools → Port menu, or Device Manager on Windows).

```bash
python main.py
```
You should see `[Silent Voice] Ready. Waiting for gestures...` — bend a finger on
the glove and you should hear the phrase spoken aloud within ~200ms.

### Step 3 — Mobile / camera device
```bash
cd mobile
pip install -r requirements.txt
```
If running on a separate device from the AI PC, find the AI PC's local IP
(`ipconfig` on Windows / `ifconfig` or `ip a` on Mac/Linux) and set `AI_PC_IP`
in `mobile_vision.py` to that address. If running on the same machine, leave it
as `localhost`.

```bash
python mobile_vision.py
```
A webcam window opens showing your detected expression (`HAPPY` / `SAD` /
`NEUTRAL`) — this now also influences which phrase gets spoken on the AI PC.

### Step 4 — Cloud AI 100
```bash
cd cloud
pip install -r requirements.txt
```
Fill in `CLOUD_ENDPOINT` and `API_KEY` in `cloud_sync.py` with your Qualcomm
Cloud AI 100 console credentials.

```bash
python cloud_sync.py
```
This runs a standalone test push using sample data and prints the response.
During the live demo, call `log_session_and_get_update(session_log)` with the
AI PC's actual `session_log` (import it directly, or expose it via a small
Flask route in `main.py` if the two need to run as separate processes).

---

## 4. Demo script (rehearse this exact order)

1. Put on the glove → open hand (`000`) → system says **"Hello"**.
2. Bend index finger (`100`) → system says **"I am thirsty."**
3. Bend all fingers (`111`) → system says **"Emergency! Call my caregiver immediately."** — your most dramatic demo beat.
4. Turn off Wi-Fi on all devices → gesture-to-speech still works (Arduino → AI PC
   is USB, not Wi-Fi) → say out loud: *"this core pipeline runs 100% offline."*
5. Turn Wi-Fi back on, show the terminal where mobile expression updates and the
   Cloud AI 100 response are logged.
6. Invite a judge to try the glove themselves.

---

## 5. Requirements summary

| Component | Install |
|---|---|
| Arduino IDE | https://www.arduino.cc/en/software |
| AI PC | `pip install -r ai-pc/requirements.txt` |
| Mobile | `pip install -r mobile/requirements.txt` (mediapipe, opencv-python, requests) |
| Cloud | `pip install -r cloud/requirements.txt` (requests) |

## 6. Stretch goals (only attempt after the MVP demo works end-to-end)

If you finish the core pipeline with real time left, upgrade in this order — each one is
independent, so stop at whichever point you run out of time and everything still demos cleanly:

1. **Coqui TTS instead of pyttsx3** — better voice quality, still runs offline on the AI PC. Swap
   the `engine.say()` calls in `main.py` for a Coqui inference call.
2. **MediaPipe Face Landmarker (GPU delegate) instead of the brightness/mouth-corner heuristic** —
   more reliable expression detection on `mobile_vision.py`.
3. **BLE instead of USB serial** between Arduino and AI PC — only attempt this if someone on the
   team already knows the `bleak` Python library or the board's BLE stack; it's the highest-risk
   swap because BLE pairing issues eat demo time fast. USB is not a weaker architecture, it's a
   more reliable one for a live judged demo.
4. **Real Cloud AI 100 endpoint + response parsing** instead of the local fallback rerank in
   `cloud_sync.py` — do this once you actually have console credentials working.
5. **NPU-accelerated inference (onnxruntime-genai / LiteRT-LM)** — this is genuinely a multi-day
   SDK learning curve. Don't attempt it live at the venue; if your team already has NPU experience
   coming in, prototype it beforehand and swap it in as a pre-tested module, not something you
   debug on stage.

Do not reorder this list under time pressure — 1 and 2 make your demo look and sound better with
low risk; 3 and 5 are what could make your demo fail live if attempted last-minute.

## License

MIT — see `LICENSE`.
