# NPU / Qualcomm-Maximized Setup — Read This Before Attempting

This layer adds NPU-accelerated intent expansion (Gemma3-1B via QNN), a second
NPU device story (FastVLM on the phone), and Arduino Bridge LED feedback, on
top of your already-working camera pipeline. **None of this replaces
`main_camera.py` — it's an optional bonus layer.**

---

## Read this first: what's realistic

- **Everything NPU-related only works on the actual Qualcomm-provided AI PC at
  the venue** (Windows ARM64, Snapdragon X Elite). It will not install or run
  on your personal Windows laptop.
- **Do not attempt to export/quantize the Gemma3-1B model live at the venue.**
  That step alone can take hours. If a pre-quantized model bundle isn't
  already downloaded before Day 1, skip the NPU LLM layer entirely.
- **The QNN tooling is bleeding-edge** — LLM support on QNN currently needs a
  nightly onnxruntime build, meaning things can break in ways unrelated to
  anything you did wrong.
- **FastVLM-0.5B on the OnePlus is a pre-built sample app, not a library you
  import.** Getting its output to POST to your AI PC over Wi-Fi is a real
  integration task, not a checkbox — budget real time for it or skip it.

**If in doubt, don't attempt it live.** Your working camera pipeline
(`main_camera.py`) already gives you a complete, honest, judge-ready demo.

---

## Priority order (matches the "honest cut-line" advice)

### Tier 0 — Always keep this running as your safety net
`main_camera.py` + `hand_gesture_camera.py` — your tested, working pipeline.
This is what you demo if nothing below works.

### Tier 1 — Try this first if you have a Snapdragon AI PC and 30 minutes
```
cd ai-pc
pip install onnxruntime onnxruntime-qnn
python npu_verify.py
```
If this prints `[SUCCESS]` — you can truthfully tell judges "we verified QNN
NPU access on the AI PC," which alone is a real, defensible technical claim,
even without running a full model on it yet.

If it prints `[FAIL]` — stop here. Don't sink more time in. Report Tier 0 only.

### Tier 2 — Only attempt if Tier 1 succeeded AND a teammate has a
pre-downloaded, pre-quantized Gemma3-1B ONNX model bundle ready (obtained
**before** the event via Qualcomm AI Hub — see below)
```
python main_npu.py
```
This is designed to fail safe: if the model doesn't load, it automatically
falls back to plain phrase lookup and your demo still works, just without
the NPU-expanded sentences. Check the terminal for:
```
[Silent Voice] NPU intent expansion: ENABLED
```
vs
```
[Silent Voice] NPU intent expansion: DISABLED (fallback active)
```

### Tier 3 — Skip unless someone already has FastVLM/LiteRT-LM experience
Getting FastVLM output from the OnePlus into your pipeline requires either:
- Building a small companion app around the FastVLM sample that POSTs its
  label to `http://<AI_PC_IP>:5000/expression` (same endpoint your existing
  `mobile_vision.py` already uses — the receiving side needs no changes), or
- Manually reading the app's output and typing it in for demo purposes only
  (acceptable to mention as a known limitation, not to hide)

### Tier 4 — Lowest priority, do only if someone has spare time
`arduino/bridge_led_feedback.ino` — ambient LED feedback via Bridge RPC.
**Verify the exact Bridge API against the UNO Q's actual documentation at the
venue first** — the code here follows the classic Arduino Bridge pattern but
UNO Q is new hardware and the API may differ. This is cosmetic polish only;
it does not affect your core functionality either way.

---

## Getting a pre-quantized Gemma3-1B bundle (do this BEFORE the event, not at the venue)

This uses Qualcomm AI Hub's model export tooling. It downloads and uploads
model data to Qualcomm's servers and can take several hours depending on your
connection — start this the night before, not day-of.

```bash
pip install qai-hub-models
python -m qai_hub_models.models.gemma3_1b_quantized.export \
  --device "Snapdragon X Elite CRD" \
  --skip-inferencing --skip-profiling \
  --output-dir ./models/gemma3-1b-qnn
```

If this command's exact model name has changed by the time you run it, search
Qualcomm AI Hub's model catalog for the current Gemma3-1B or equivalent small
quantized LLM entry — model names on AI Hub are updated periodically.

---

## What to say to judges — calibrated to what you actually got working

**If only Tier 0 works:** describe your real architecture honestly — 4 devices,
offline core pipeline, sub-200ms gesture-to-speech. This is a complete,
legitimate submission on its own.

**If Tier 1 succeeds but not Tier 2:** "We verified QNN NPU access is available
on the Snapdragon AI PC as part of our technical validation — full on-NPU
inference is our next integration step."

**If Tier 2 fully works:** the scripted line from the original doc is accurate
to use: on-device NPU inference, quantized, verified via `get_ep_devices()`,
sub-200ms, fully offline.

**Never claim NPU usage you haven't actually verified running.** A judge who
asks "can you show me it's running on NPU, not falling back to CPU?" and gets
a shrug will cost you more credibility than not claiming NPU at all.
