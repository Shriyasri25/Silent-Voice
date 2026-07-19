# Silent Voice — How to Demonstrate to Judges

A demo lives or dies on staging and timing, not just working code. Follow this.

---

## 1. Physical setup (5–10 minutes before judges arrive)

- **Table layout, left to right:** glove + Arduino (closest to where a judge will stand) →
  AI PC laptop (screen angled so judges can see the terminal) → phone/second laptop running
  the webcam script, positioned facing the person wearing the glove.
- **Start both scripts running BEFORE judges reach your table** (`main.py`, then
  `mobile_vision.py`). Nothing kills momentum like debugging while judges wait.
- **Volume up.** Test that speech is audible over hackathon floor noise.
- **Have the glove pre-worn or easy to slip on** — don't fumble with sensor tape live.
- **Close every other window/app** so your screen only shows what matters.
- **One team member is the presenter, one is the "patient" wearing the glove.** Decide this
  in advance — don't sort it out in front of judges.

---

## 2. The demo flow (aim for under 3 minutes total)

Practice this exact sequence 5+ times before Day 2. Time yourselves.

**Beat 1 — The hook (15 sec)**
> "70 million people worldwide can't speak — due to ALS, cerebral palsy, stroke, autism.
> Silent Voice gives them a voice using 4 devices working together."

**Beat 2 — Live gesture demo (45 sec)**
- Open hand → *(system says "Hello")*
- Bend index finger → *(system says "I am thirsty.")*
- Bend all fingers → *(system says "Emergency! Call my caregiver immediately.")*
- Narrate while it happens: *"Three flex sensors on the glove map to 8 phrases, spoken
  in under 200 milliseconds — no delay, no lag."*

**Beat 3 — The offline moment, your showstopper (30 sec)**
- Physically turn off Wi-Fi on the AI PC (or airplane mode on the phone).
- Repeat a gesture — it still speaks instantly.
- Say clearly: *"This isn't a cloud demo. The gesture-to-speech pipeline runs entirely
  on-device — critical for rural clinics and homes with unreliable internet."*
- Turn Wi-Fi back on.

**Beat 4 — Multi-device story (30 sec)**
- Point at the camera window: *"The mobile layer reads facial expression in parallel,
  adding context to the phrase selection."*
- Point at the terminal: *"Every session is logged and synced to Cloud AI 100, which
  reranks phrases based on what this specific person actually uses most — personalization
  without ever blocking the real-time pipeline."*

**Beat 5 — Let a judge try it (30–45 sec)**
- Hand them the glove. Let them make a gesture themselves.
- This is the single highest-impact moment for the Popularization Award — people remember
  what they touched, not what they watched.

**Beat 6 — Close (10 sec)**
> "Four devices, one seamless experience, giving someone back their voice. Thank you."

---

## 3. What to have ready on-screen

- Terminal running `main.py` visible, showing live gesture/phrase/latency logs
- Webcam window visible, showing expression label updating
- GitHub repo open in a browser tab, in case judges ask to see code
- README open to the gesture table, in case they ask "what does each gesture mean?"

---

## 4. Likely judge questions — have answers ready

| Question | Answer |
|---|---|
| "What happens if the sensor gives a bad reading?" | The code only speaks when the gesture is a valid 3-bit code and has changed from the last one — debounced to avoid misfires. |
| "Why only 8 gestures?" | Balances expressiveness with reliability — 3 sensors keeps the hardware simple and every combination is unambiguous, unlike continuous gesture recognition which is harder to get right in 24 hours. |
| "Is this actually personalized per user?" | Session data (gesture, expression, phrase, whether it was used) is logged and sent to Cloud AI 100, which reranks phrase predictions per user over time. |
| "What's the latency?" | Sub-200ms from gesture to spoken audio, entirely on-device for the core loop. |
| "Could this scale to more phrases?" | Yes — the phrase bank is a simple JSON lookup; more sensors or a bigger gesture vocabulary just means more entries, no architecture change. |
| "What's next if you had more time?" | Point to your stretch goals: better TTS voice quality, more reliable expression detection, and eventually NPU-accelerated on-device inference. |

---

## 5. Backup plans — decide these NOW, not mid-demo

- **If the flex sensor glove misbehaves live:** have a 30-second screen-recorded video of a
  clean run on your phone, ready to play instantly. Say "here's a recording from our testing
  in case the sensor needs recalibration" — judges respect honesty over silent fumbling far
  more than a failed live attempt.
- **If Wi-Fi/network is flaky at the venue:** the offline moment (Beat 3) actually protects
  you here — your core pipeline doesn't depend on the venue network at all.
- **If the webcam won't open:** skip Beat 4's camera part, keep going. The core demo (Beats
  1–3, 5, 6) stands on its own without it.
- **If someone asks a question you can't answer confidently:** "That's something we'd want
  to validate further — right now our focus was proving the core multi-device pipeline
  works reliably." Confident honesty beats a shaky guess.

---

## 6. Team roles during the demo

| Role | Who | Job |
|---|---|---|
| Presenter | 1 person | Talks, narrates, handles Q&A |
| Glove wearer | 1 person | Performs gestures on cue, stays quiet unless asked |
| Tech support | 1–2 people | Stand back, ready to restart a script silently if something crashes — don't interrupt the presenter |
| Judge wrangler | Remaining | Makes eye contact with approaching judges, invites them over, hands them the glove for Beat 5 |

---

## 7. The one thing that matters most

Judges see dozens of demos in a row. What they remember is **what they physically did**,
not what they watched. Get a judge's hands on that glove every single time. That's what
turns "a working prototype" into "the project I remember."
