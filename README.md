# Silent Voice
 
> A real-time, **offline** talking aid for people who can't speak — driven by
> **hand gestures** and **facial expression**, running on **Qualcomm on-device
> AI**. No glove. No sensors. Just a camera.
 
**Snapdragon Multiverse Hackathon 2026 · Qualcomm Noida Campus**
 
---
 
## 📖 Contents
 
- [What is Silent Voice?](#-what-is-silent-voice)
- [How It Works](#️-how-it-works)
- [The Gestures](#-the-gestures)
- [Devices Used](#-devices-used)
- [Team](#-team)
- [Setup](#️-setup-from-scratch)
- [Run & Usage](#️-run--usage)
- [Testing](#-testing)
- [Notes](#-notes)
- [References](#-references)
- [License](#-license)
---
 
## 🎯 What is Silent Voice?
 
Plenty of people have things to say and no way to say them. A stroke, ALS,
cerebral palsy, or being non-verbal on the autism spectrum can take away speech
while leaving every thought behind it intact. Around **70 million people** live
this way.
 
The tools that give that speech back usually cost lakhs and expect a steady
internet connection — which quietly rules out most of the people who need them,
especially outside the big cities.
 
Silent Voice goes the other way. You make a hand gesture in front of a camera. It
reads the gesture, reads your face, and says a phrase out loud — in a fraction of
a second, with the internet switched off. There's nothing to put on: no glove, no
wires, no sensors. A webcam and free software, on hardware a clinic might already
own.
 
---
 
## ⚙️ How It Works
 
```
        YOU MAKE A GESTURE
              │
              ▼
   ┌────────────────────┐
   │   1 · CAMERA        │   MediaPipe reads which fingers are up,
   │   gesture + face    │   and reads your expression at the same time
   └─────────┬──────────┘
              │
              ▼
   ┌────────────────────┐
   │   2 · AI PC         │   Fuses the gesture with the expression and
   │   picks the phrase  │   picks the phrase — on the Snapdragon NPU
   └─────────┬──────────┘
              │
              ▼
   ┌────────────────────┐
   │   3 · SPEECH        │   Says it out loud, offline —
   │   spoken aloud      │   English, or Hindi via Sarvam AI
   └─────────┬──────────┘
              │
              ▼
   ┌────────────────────┐
   │   4 · CAREGIVER     │   Arduino light goes 🟢 green for calm,
   │   LED (urgency)     │   🔴 red for urgent — readable across the room
   └────────────────────┘
 
   ═══════════════════════════════════════════════════════════════
   Everything above runs on-device. Switch off the Wi-Fi — it still
   works. The only networked part is optional:
   ───────────────────────────────────────────────────────────────
              ┆ (async, in the background)
              ▼
   ┌────────────────────┐
   │   Cloud AI 100      │   Learns your vocabulary over time and reranks
   │   (optional)        │   phrases. Unplug it and nothing breaks.
   └────────────────────┘
```
 
Four steps, and the first three never touch the internet.
 
The idea that makes it feel human: **the same gesture says different things
depending on your face.** A fist with a calm face asks for help; the same fist
with a distressed face says you're in pain. So a person learns a handful of
gestures and can still say a lot.
 
---
 
## ✋ The Gestures
 
Everything is read from the camera with **Google MediaPipe** — no wearable, no
calibration. Six gestures, each crossed with the person's expression:
 
| Gesture | 😐 Neutral | 🙂 Happy | 😢 Sad |
|---|---|---|---|
| **Open hand** | I need water | Yes, thank you | I am not feeling well |
| **Fist** | I need help | I am feeling better | I am in pain |
| **Pinch** | Please wait | I am okay | I need medicine |
| **Point** | Look at that | — | It hurts here |
| **Peace** | Goodbye | Thank you so much | — |
| **Thumb** | Yes | — | No |
 
> When a gesture-and-face pair isn't defined, it falls back to that gesture's
> neutral phrase, so a conversation never stalls. A sad face also turns the
> caregiver light red on its own.
 
Phrases live in a plain file — `ai-pc/phrases.json.txt` — so you can reword them
without touching any code.
 
---
 
## 💻 Devices Used
 
| Device | What it does |
|---|---|
| **Surface Laptop 7** (Snapdragon X Elite) | The brain. Reads gestures, fuses them with the expression, generates the phrase on the **Hexagon NPU** via ONNX Runtime, and speaks it. |
| **OnePlus 15** (Snapdragon 8 Elite) | Reads facial expression on its **Hexagon NPU** and sends the label to the laptop over the local network. |
| **Arduino UNO Q** | Drives the green/red caregiver light. |
| **Qualcomm Cloud AI 100** | *(optional)* Learns a user's patterns and reranks their phrases in the background. Never blocks the offline loop. |
 
The real-time work runs **on Qualcomm NPU silicon — not the cloud, not the CPU** —
and the core loop keeps working with the network off.
 
---
 
## 👥 Team
 
| Name | Email |
|---|---|
| Shriya Srivastava | shriyasrivastava025@gmail.com |
| Pranav Tyagi | tyagipranav10@gmail.com |
| Aniket Prasad | aniketprasadn@gmail.com |
| Ansh Varshney | varshneyansh9267@gmail.com |
| Shubham Chauhan | shubham.23b0231028@abes.ac.in |
 
---
 
## 🛠️ Setup (from scratch)
 
**Before you start**
 
- A Windows laptop with **Python 3.10**
- A working **webcam** (built-in or USB)
- *(Optional)* an Arduino UNO Q, a green and a red LED, two 220Ω resistors
- *(Optional)* Arduino App Lab — https://www.arduino.cc/en/uno-q
> The app runs on the webcam alone. The Arduino and the phone are extras that add
> the caregiver light and the expression fusion — skip them and it still talks.
 
**Step 1 — Get the code**
 
```bash
git clone https://github.com/YOUR-USERNAME/silent-voice.git
cd silent-voice
```
 
**Step 2 — Install the dependencies**
 
```bash
python -m pip install -r requirements.txt
```
 
Two or three minutes, once.
 
| Package | Why it's here |
|---|---|
| `mediapipe` | reads hand gestures and face landmarks from the camera |
| `opencv-python` | grabs the webcam feed |
| `pyttsx3` | speaks the phrases, fully offline |
| `numpy` | the small bit of math the gesture logic needs |
 
On the Snapdragon X Elite, add the NPU pieces to switch on on-device phrase
generation:
 
```bash
python -m pip install onnxruntime-genai onnxruntime-qnn
```
 
> Leave these out and it still runs — it just uses the fixed phrase table instead
> of the NPU model, so it demos fine on any laptop.
 
**Step 3 — (Optional) Wire up the Arduino UNO Q**
 
1. Open **Arduino App Lab** and load `sketch/sketch.ino`.
2. Wire the LED: Red → pin **9**, Green → pin **10**, Blue → pin **11**, each
   through a 220Ω resistor to GND.
3. Hit **Run**. The Python side now drives the light over the Bridge.
---
 
## ▶️ Run & Usage
 
```bash
python main.py
```
 
A camera window opens. Hold a gesture, hear the phrase. Press **`q`** to quit.
The window shows the gesture and expression it's reading, and the phrase it's
about to say. If the Arduino is connected, its light changes colour with the
urgency.
 
**Try these first:**
 
- **Open hand** (neutral) → "I need water"
- **Fist** (sad face) → "I am in pain"
- **Peace sign** → "Goodbye"
- **Thumbs up** → "Yes"
---
 
## ✅ Testing
 
**1 — Core app, webcam only.** Run `python main.py`, show an open hand → you
should hear *"I need water."* If that works, the main loop is healthy.
 
**2 — Confirm it's really on the NPU.**
```bash
python -c "from main import verify_npu; verify_npu()"
```
On the Snapdragon X Elite this prints `NPU device found: True`. We check this on
purpose — a model can quietly fall back to the CPU and still look like it's
working, while losing all the speed the NPU is there for. Latency prints on every
phrase.
 
**3 — Arduino light (optional).** Run the sketch, then `main.py`. A sad face or a
fist turns the light red; a calm gesture turns it green.
 
**4 — Offline (the one that matters).** Turn off Wi-Fi and make a gesture. It
still speaks. That's the whole point of the project in a single test.
 
---
 
## 📝 Notes
 
**Why there's nothing to wear.** Traditional AAC devices can run ₹3–5 lakh per
user and often lean on the cloud. Ours needs a webcam and free software on
Qualcomm hardware a clinic may already have — no per-user hardware, no internet in
the core loop. That's the gap between a device a rural centre can afford and one
it can't.
 
**Sarvam AI for Indian languages.** We wired in **Sarvam AI** so phrases can be
spoken in Hindi and other Indian languages, not just English — which is what turns
this from a demo into something people here would actually use.
 
**ONNX Runtime on the NPU.** Phrase generation runs through `onnxruntime-genai`
on the Snapdragon X Elite Hexagon NPU. We verify the execution provider directly
(see test 2) instead of assuming a clean load means it's on the NPU.
 
**The cloud piece stays out of the way.** Cloud AI 100 personalization runs
asynchronously and only improves future suggestions. Cut it off and nothing in
the live path notices.
 
**Honest about the edges.** Expression reading is a heuristic, so rough lighting
can fool it. Gesture thresholds may want a quick tweak for very different hands.
And we'd always rather show the working version than a fancier one that breaks on
stage.
 
---
 
## 📚 References
 
- Qualcomm AI Hub — https://aihub.qualcomm.com
- Qualcomm Simple NPU Chatbot (NPU inference reference) — https://github.com/thatrandomfrenchdude/simple_npu_chatbot
- Arduino UNO Q — https://www.qualcomm.com/developer/hardware/arduino-uno-q
- Arduino UNO Q Project Hub — https://projecthub.arduino.cc/?value=UNO+Q
- Google MediaPipe — https://developers.google.com/mediapipe
- LiteRT / LiteRT-LM — https://ai.google.dev/edge/litert
- Sarvam AI — https://www.sarvam.ai
- ONNX Runtime GenAI — https://github.com/microsoft/onnxruntime-genai
- Google AI Edge Gallery (FastVLM) — https://github.com/google-ai-edge/gallery
- Windows on Snapdragon AI Developer Docs — https://docs.qualcomm.com/bundle/publicresource/topics/80-62010-1/ai-appdevelopment.html
---
 
## 📄 License
 
**MIT** — see [LICENSE](LICENSE). Use it, change it, ship it. If it gets a voice
to someone who needs one, that's the point.
