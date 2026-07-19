# Silent Voice — FINAL STEP-BY-STEP (OnePlus 15R Camera Setup)

This is the current, final way to run the project: **OnePlus 15R phone as the
camera/gesture input**, no flex sensors needed. Follow every step in order.

---

## PART 1 — One-time setup (do this once)

### 1.1 Install Python (skip if already done)
python.org/downloads → install Python 3.11+. **Check "Add python.exe to PATH"**
during install.

### 1.2 Install "IP Webcam" on the OnePlus 15R
Open Play Store on the phone → search **"IP Webcam"** by Pavel Khlebovich → Install.

### 1.3 Install project Python packages
Open File Explorer → go to your project's `ai-pc` folder → click the address bar →
type `cmd` → Enter. In the terminal that opens:
```
pip install -r requirements.txt
```
Then go to the `mobile` folder the same way and run:
```
pip install -r requirements.txt
```

---

## PART 2 — Every time you demo (do these steps each session)

### Step 1 — Connect phone and laptop to the SAME Wi-Fi
Both devices must be on the same network. Check this first — it's the #1 cause of
connection failures.

### Step 2 — Start the camera stream on the phone
1. Open **IP Webcam** app on the OnePlus 15R
2. Scroll down → tap **Start server**
3. The screen shows an address like `http://192.168.1.42:8080`
4. **Write down that IP address** (yours will be different)

### Step 3 — Point the script at the phone
On the laptop, open `silent-voice\mobile\hand_gesture_camera.py` in Notepad. Find:
```python
CAMERA_SOURCE = 0
```
Change it to your phone's address with `/video` added:
```python
CAMERA_SOURCE = "http://192.168.1.42:8080/video"
```
Save and close.

### Step 4 — Start the AI PC brain (camera version — no Arduino needed)
Open a terminal in `silent-voice\ai-pc`:
```
python main_camera.py
```
You should see:
```
[Silent Voice] Camera mode — no Arduino needed.
[Silent Voice] Waiting for gestures from hand_gesture_camera.py...
```
**Leave this terminal running.**

### Step 5 — Start the gesture camera script
Open a **second, new** terminal in `silent-voice\mobile`:
```
python hand_gesture_camera.py
```
A window opens showing the OnePlus phone's live camera feed with your hand
skeleton drawn on it, and a live code in the corner (e.g. `Code: 000`).

### Step 6 — Test all 8 gestures
Hold your hand up in front of the phone camera and check each one speaks correctly:

| Show this | Code | Should hear |
|---|---|---|
| Open hand | `000` | "Hello" |
| Bend index only | `100` | "I am thirsty." |
| Bend middle only | `010` | "I need food." |
| Bend ring only | `001` | "I need medicine." |
| Bend index + middle | `110` | "Please help me." |
| Bend index + ring | `101` | "Please call the doctor." |
| Bend middle + ring | `011` | "I need my wheelchair." |
| Bend all three | `111` | "Emergency! Call my caregiver immediately." |

If a gesture doesn't register correctly, keep your hand fully in frame, fingers
spread apart when "open," and make sure lighting is decent — no strong backlight
behind your hand.

---

## PART 3 — Optional: mobile expression layer (extra polish)

This is separate from the gesture camera and adds a second signal (facial
expression), logged alongside each gesture. Only do this after Part 2 works.

If you're using the OnePlus phone for gestures already, run this on the **laptop's
own webcam** instead (leave `CAMERA_SOURCE = 0` in `mobile_vision.py`), so you're
not trying to use one phone for two things at once.

Open a **third** terminal in `silent-voice\mobile`:
```
python mobile_vision.py
```

---

## PART 4 — Optional: Cloud AI 100 sync

Open a terminal in `silent-voice\cloud`:
```
pip install -r requirements.txt
```
Fill in `CLOUD_ENDPOINT` and `API_KEY` in `cloud_sync.py` from your Qualcomm
console, then:
```
python cloud_sync.py
```

---

## PART 5 — If you get the flex sensor glove working later

You don't lose anything — `arduino/glove_firmware.ino` and `ai-pc/main.py` (the
original serial version) are untouched. Just run `main.py` instead of
`main_camera.py`, and use the Arduino instead of the phone camera. Both versions
use the exact same `phrases.json`, so the phrase table doesn't need to change
either way.

---

## PART 6 — Demo day checklist

- [ ] Phone and laptop on the same Wi-Fi, confirmed **before** judges arrive
- [ ] IP Webcam server started on the phone, address noted
- [ ] `CAMERA_SOURCE` in `hand_gesture_camera.py` set to the phone's current IP
      (it may change if the phone reconnects to Wi-Fi — recheck it each morning)
- [ ] `main_camera.py` running and showing "Waiting for gestures..."
- [ ] `hand_gesture_camera.py` running, camera window showing the phone's feed
- [ ] All 8 gestures tested and speaking correctly
- [ ] Phone propped on a stand facing the glove-wearer's hand — steadier than
      someone holding it
- [ ] Volume up, laptop not on silent/muted

See `DEMO_GUIDE.md` for the full presentation script and judge Q&A prep.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Camera window won't open / blank | Check phone and laptop are on the same Wi-Fi; re-check the IP address shown in IP Webcam (it can change) |
| "Connection refused" or timeout | IP Webcam server not started on the phone, or wrong IP typed into `CAMERA_SOURCE` |
| Gestures detected but wrong phrase | Check `phrases.json` matches the code shown on-screen exactly |
| Hand not detected at all | Improve lighting, move hand fully into frame, avoid busy/cluttered background |
| No sound | Check laptop volume; test `pyttsx3` works standalone first |
