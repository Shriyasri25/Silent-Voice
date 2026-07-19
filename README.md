# Silent Voice 

Multi-device AAC (Augmentative & Alternative Communication) system for the Snapdragon Multiverse Hackathon. A gesture glove speaks for the user, a camera reads their expression to refine the phrase, and a cloud service personalizes their vocabulary over time.

**Team:** Shriya (Lead) + 4 members — add all 5 names + emails here before submission. 

--- 

## 1. How the pieces fit

**There are two version of this architecture, know which one you are showing:**

| Pitch-deck architecture (slides, PDF) | What is actually built here (this repo) |
| **Hardware** | **AI Model** | **Notes** | |---|---|---| | Arduino | STM32 MCU + QRB2210 MPU, Bridge RPC, BLE | Single Arduino UNO Q, USB serial | | Mobile | OnePlus 15, FastVLM-0.5B on Hexagon NPU via LiteRT-LM | Any webcam device, MediaPipe FaceMesh (CPU) | | AI PC | onnxruntime-genai on Surface Laptop NPU | Plain Python, pyttsx3 TTS (CPU) | | Cloud | Qualcomm AI Inference Suite, model-delta push | Simple REST POST/response, local fallback rerank | | Connectivity | BLE (glove↔hub) + Wi-Fi (mobile↔hub) | USB serial (glove↔hub) + Wi-Fi (mobile↔hub) |

** Why the gap is intentional, not a shortcut you should hide: the pitch deck describes the NPU-optimized, production version of Silent Voice — the thing you'd build with weeks and a Qualcomm SDK deep-dive. This repo contains the same *system design* (4 devices, same data flow, same phrase/gesture table) built with tools that a beginner team can actually get working and demo reliably in 24 hours. Judges want to see that your architecture is sound and that your demo works live — not that every box uses the most fancy possible runtime. If you finish the core MVP with time to spare, the order to attempt real NPU/BLE upgrades is in the "Stretch goals" section below.

**Data flow (same for both versions):**

``` 
┌────────────────┐ USB serial ┌────────────────────┐
│ Arduino UNO Q │ ───────────────▶ │ AI PC (main.py) │ │ (flex sensors) │ "000"/"111" │ - decodes phrase │
└────────────────┘ etc. │ - Talks through pyttsx3 |  - Flask :5000 |
┌────────────────┐    HTTP POST │ - logs session │ │ Mobile / camera │ ─────────────────▶│ │
│ (mobile_vision.py)│ {expression} └──────────┬───────────┘
└────────────────┘ │ │ session_log ▼ ┌─────────────────────┐
                                       ``` ┌──────────────────────┐ │ cloud_sync.py (Cloud AI 100) │ │ personalization/reranking │ └──────────────────────┘ ```

- **Arduino → AI PC:** USB cable, plain serial text lines (a gesture label per line).- **Mobile → AI PC:** Wi-Fi, both devices on local network. Mobile script sends JSON via POST to `http://<AI_PC_IP>:5000/expression`.- **AI PC → Cloud AI 100:** HTTPS, `cloud_sync.py` pushes the accumulated `session_log` list, and prints back whatever personalization the cloud returns.

--- 

## 2. Hardware wiring (Arduino UNO Q) - 3 Flex Sensors, 8 Gestures

If you have flex sensors use them, potentiometers are an alternative for testing and work exactly the same.

Wire each of the 3 sensors as a voltage divider:
``` 5V ───── sensor ─────┬──── Analog Pin (A0/A1/A2) │ 10kΩ resistor │ GND ```

| Sensor | Finger | Arduino pin | |--------|---------|-------------| | 1 | Index | A0 | | 2 | Middle | A1 | | 3 | Ring | A2 |

Tape the sensors on the glove, finger by finger, so that each finger bends to change the analog reading. Upload the firmware and open Serial Monitor at 9600 baud. You should see a 3-digit code (e.g. `000`, `100`, `111`) printed as you bend fingers. If not, re-calibrate `BEND_THRESHOLD` in `glove_firmware.`ino` if the resting values of your sensors are very different (higher reading = straight, lower = bent).

### Last 8 Gestures | Code | Gesture | Voice Output | Category | |------|------------------------|---------------------------------------------|---------------------| | 000 | Open Hand | "Hello" | Greeting | | 100 | Index Bent | "I am thirsty." | Daily Need | | 010 | Middle Bent | "I need food." | Daily Need | | 001 | Ring Bent | "I need medicine."                           | Medical | | 110 | Index + Middle | "Please help me." | Emergency | | 101 | Index + Ring | "Please call the doctor." | Medical Emergency | | 011 | Middle + Ring | "I need my wheelchair.                      | Mobility | | 111 | All Bent | "Oh no! Call my caregiver right away." | Critical Emergency |

Code bit order is always ** Index, Middle, Ring ** ( ` 0 ` = straight, ` 1 ` = bent ).

--- 

## 3. Setup - Run in this sequence

### Step 1 - Arduino
1. In the Arduino IDE, open the arduino/glove_firmware.ino file.
2. Choose the proper board (Arduino UNO Q) and port.
3. Upload. 
4. Open Serial Monitor (9600 baud) and check that your gesture labels print when you bend fingers. Close Serial Monitor afterwards , only one program can hold the port at a time .

### Step 2 — AI PC ```bash cd ai-pc pips install -r requirements.txt ``` Change `SERIAL_PORT` in `main.py` to your Arduino's port (check in the Arduino IDE's Tools → Port menu, or Device Manager on Windows).

python main.py You should see `[Silent Voice] Ready. Waiting for gestures...` -- bend a finger on the glove and you should hear the phrase spoken out loud in ~200ms.

### Step 3 — Mobile / camera device ```bash cd mobile pips install -r requirements.txt ``` If you are running on a different device to the AI PC, find the AI PC's local IP (`ipconfig` on Windows / `ifconfig` or `ip a` on Mac/Linux) and change `AI_PC_IP` in `mobile_vision.py` accordingly. If running on the same machine, leave it as `localhost`.

```bash python mobile_vision.py ``` You see a window with your detected expression (`HAPPY` / `SAD` / `NEUTRAL`) on the webcam, which now also influences what is spoken on the AI PC.

### Step 4 — Cloud AI 100 ```bash cd cloud pip setup -r requirements.txt ``` In `cloud_sync.py`, replace `CLOUD_ENDPOINT` and `API_KEY` with your Qualcomm Cloud AI 100 console credentials. ```bash python cloud_sync.py ```
This will push once with some sample data and print the response.
During the live demo, call `log_session_and_get_update(session_log)` with the actual `session_log` of the AI PC (import it directly, or expose it through a small Flask route in `main.py` if the two have to run as separate processes).

--- 

## 4. Demo script (practice this exact order)

1. Put on the glove → open hand (`000`) → system says **"Hello"**
2. Curved index finger (`100`) → system says **"I am thirsty."**
3. Fold all fingers (`111`) → system says **"Emergency! Call my caregiver immediately."** — your most dramatic demo beat.
4. turn off Wi-Fi on all devices -> gesture-to-speech still works (Arduino -> AI PC is USB, not Wi-Fi) -> say out loud: *"this core pipeline runs 100% offline."* 5. turn Wi-Fi back on, show the terminal where mobile expression updates and the Cloud AI 100 response are logged.
6. Have the judge try on the glove themselves.
--- 

## 5. Requirements summary | Component | Install | |---|---| | Arduino IDE | https://www.arduino.cc/en/software | | AI PC | python install -r ai-pc/requirements.txt` | | Mobile | python install -r mobile/requirements.txt` (mediapipe, opencv-python, requests) | | Cloud | python install -r cloud/requirements.txt` (requests) | 

## 6. Stretch goals (only after the MVP demo works end to end)

If you finish the core pipeline and real time remains, upgrade in this order, each one is independent, so stop at whichever point you run out of time and everything still demos cleanly:

1. **Coqui TTS instead of pyttsx3** – better voice quality, and still works offline on the AI PC. Replace the `engine.say()` calls in `main.py` with a Coqui inference call.
2. **MediaPipe Face Landmarker (GPU delegate) instead of the brightness/mouth-corner heuristic** — more reliable expression detection on `mobile_vision.py`.
3. **BLE instead of USB serial** between Arduino and AI PC — only try if someone on the team already knows the `bleak` Python library or the board's BLE stack; it is the riskiest swap because BLE pairing problems can eat demo time quickly. USB is not a weaker architecture it is a more reliable one for a live judged demo.
4. **Real Cloud AI 100 endpoint + response parsing** instead of the local fallback rerank in `cloud_sync.py` — do this when you actually have console credentials working.
5. **NPU-accelerated inference (onnxruntime-genai / LiteRT-LM)** – this is a real multi-day SDK learning curve. don't try to do it live at the venue. If your team has NPU experience already coming in, prototype it ahead of time and swap it in as a pre-tested module, not something you debug on stage.

Do not reorder this list under time pressure — 1 and 2 make your demo look and sound better with low risk; 3 and 5 are what could make your demo fail live if attempted at the last minute. ## License

MIT -- see LICENSE.
