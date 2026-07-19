"""
Silent Voice — NPU-accelerated version (Gemma3-1B via onnxruntime-genai on QNN)

Adds an NPU-powered intent-expansion layer on top of your working pipeline:
gesture code -> base phrase (same phrases.json) -> Gemma3-1B on NPU expands
it into a more natural sentence -> spoken aloud.

CRITICAL DESIGN CHOICE: this NEVER blocks or breaks your demo. If the NPU
model isn't available for any reason (not on Snapdragon hardware, model not
downloaded, QNN EP missing), it silently falls back to speaking the plain
phrase from phrases.json — exactly like main_camera.py already does. Your
demo cannot fail because of this file; it can only get better if the NPU
path works.

Requires (only works on the venue's Snapdragon AI PC):
  pip install onnxruntime onnxruntime-qnn onnxruntime-genai
  A pre-downloaded, pre-quantized Gemma3-1B ONNX model directory
  (exported via Qualcomm AI Hub — see NPU_SETUP.md). Do NOT attempt to
  export/quantize this live at the venue — it can take hours.

Run:
  python npu_verify.py         # confirm NPU is available FIRST
  python main_npu.py           # then run this
"""

import json
import threading
import time

from flask import Flask, request

from speech import get_engine, get_speech_status

FLASK_PORT = 5000

# Path to your pre-downloaded, pre-quantized Gemma3-1B ONNX model directory.
# See NPU_SETUP.md for how to obtain this via Qualcomm AI Hub BEFORE the event.
MODEL_PATH = "./models/gemma3-1b-qnn"

with open("phrases.json") as f:
    PHRASES = json.load(f)

# Speech engine is initialised once here; it reads .env automatically.
_speech = get_engine()

app = Flask(__name__)
current_expression = "NEUTRAL"
last_gesture = None
session_log = []

# ---- Try to load the NPU model. Falls back gracefully if unavailable. ----

npu_model = None
npu_available = False

try:
    import onnxruntime_genai as og

    npu_model = og.Model(MODEL_PATH)
    npu_tokenizer = og.Tokenizer(npu_model)
    npu_available = True
    print("[Silent Voice] NPU model loaded successfully — intent expansion ENABLED.")
except Exception as e:
    print(f"[Silent Voice] NPU model not available ({e})")
    print("[Silent Voice] Falling back to plain phrase lookup — demo will still work.")


def expand_with_npu(base_phrase: str, expression: str) -> str:
    """Use Gemma3-1B on NPU to expand a short phrase into a fuller sentence,
    informed by detected expression. Falls back to the base phrase on any error."""
    if not npu_available:
        return base_phrase

    try:
        prompt = (
            f"Rewrite this as one short, natural spoken sentence for an AAC "
            f"device. Keep the same meaning. Person seems {expression.lower()}. "
            f'Phrase: "{base_phrase}"\nSentence:'
        )
        params = og.GeneratorParams(npu_model)
        params.set_search_options(max_length=40, temperature=0.3)
        input_tokens = npu_tokenizer.encode(prompt)
        generator = og.Generator(npu_model, params)
        generator.append_tokens(input_tokens)

        output_tokens = []
        while not generator.is_done():
            generator.generate_next_token()
            output_tokens.append(generator.get_next_tokens()[0])

        result = npu_tokenizer.decode(output_tokens).strip()
        return result if result else base_phrase
    except Exception as e:
        print(f"[Silent Voice] NPU generation failed ({e}) — using base phrase.")
        return base_phrase


# ---- Standard pipeline (same as main_camera.py) ----

def speak(phrase: str):
    # Delegates to SpeechEngine — tries Sarvam AI, auto-falls back to pyttsx3.
    _speech.speak(phrase)


def resolve_base_phrase(gesture_code: str) -> str:
    return PHRASES.get(gesture_code, "I need help")


def handle_gesture(gesture_code: str):
    global last_gesture

    if gesture_code == last_gesture:
        return
    last_gesture = gesture_code

    t0 = time.time()
    base_phrase = resolve_base_phrase(gesture_code)
    final_phrase = expand_with_npu(base_phrase, current_expression)
    speak(final_phrase)
    latency_ms = int((time.time() - t0) * 1000)

    entry = {
        "gesture": gesture_code,
        "expression": current_expression,
        "base_phrase": base_phrase,
        "final_phrase": final_phrase,
        "npu_used": npu_available,
        "latency_ms": latency_ms,
        "timestamp": time.time(),
        "speech_status": get_speech_status(),
    }
    session_log.append(entry)

    print(
        f"gesture={gesture_code:<6} expression={current_expression:<8} "
        f"npu={'YES' if npu_available else 'no ':<3} "
        f"phrase='{final_phrase}'  latency={latency_ms}ms"
    )


@app.route("/gesture", methods=["POST"])
def receive_gesture():
    code = request.json.get("gesture", "")
    if len(code) == 3 and all(c in "01" for c in code):
        handle_gesture(code)
    return "OK"


@app.route("/expression", methods=["POST"])
def update_expression():
    global current_expression
    current_expression = request.json.get("expression", "NEUTRAL")
    return "OK"


def main():
    print(f"[Silent Voice] NPU mode — Flask listening on :{FLASK_PORT}")
    print(f"[Silent Voice] NPU intent expansion: {'ENABLED' if npu_available else 'DISABLED (fallback active)'}")
    app.run(port=FLASK_PORT, host="0.0.0.0")


if __name__ == "__main__":
    main()
