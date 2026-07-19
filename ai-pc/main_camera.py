"""
Silent Voice — AI PC brain (CAMERA VERSION, no Arduino needed)

Same as main.py but receives gesture codes over HTTP from
hand_gesture_camera.py instead of reading Arduino serial. Use this if
your flex sensor glove isn't working — the rest of the pipeline
(phrase lookup, TTS, session logging) is identical.

Run:
  pip install -r requirements.txt
  python main_camera.py

Then, in a second terminal:
  cd ../mobile
  python hand_gesture_camera.py

Performance optimizations applied
----------------------------------
  - speak() runs on a dedicated background thread via a queue(maxsize=1).
    Flask handlers return in <1 ms regardless of TTS duration (Sarvam ~200 ms,
    pyttsx3 ~1–3 s).  The camera script never backs up waiting for a response.
  - Queue size = 1: if a phrase is already being spoken, the next gesture is
    queued. If another gesture arrives before the queued one is consumed it
    replaces it — stale phrases are never spoken out of order.
  - Duplicate gesture guard remains: identical consecutive codes are ignored
    before they even reach the speech queue.
  - session_log.append() is done on the speech thread so it always reflects
    actual speak latency rather than enqueue latency.
"""

import json
import queue
import threading
import time

from flask import Flask, request

from speech import get_engine, get_speech_status

FLASK_PORT = 5000

with open("phrases.json") as f:
    PHRASES = json.load(f)

# Speech engine — initialised once; reads .env automatically.
_speech = get_engine()

app = Flask(__name__)

current_expression = "NEUTRAL"
last_gesture       = None
session_log        = []

# ---------------------------------------------------------------------------
# Background speech worker
# ---------------------------------------------------------------------------
# Queue size = 1:
#   slot 0 → currently being spoken (worker holds it)
#   slot 1 → next phrase waiting
# A put_nowait() that would overflow simply replaces by get + put, ensuring
# the most-recent gesture always wins without unbounded queue growth.
# ---------------------------------------------------------------------------

_speech_queue: queue.Queue = queue.Queue(maxsize=1)


def _speech_worker() -> None:
    """Drain _speech_queue, speak each phrase, append to session_log."""
    while True:
        item = _speech_queue.get()          # blocks until a phrase arrives
        gesture_code, phrase, expression = item
        try:
            t0 = time.time()
            _speech.speak(phrase)
            latency_ms = int((time.time() - t0) * 1000)

            entry = {
                "gesture":        gesture_code,
                "expression":     expression,
                "phrase":         phrase,
                "latency_ms":     latency_ms,
                "timestamp":      time.time(),
                "speech_status":  get_speech_status(),
            }
            session_log.append(entry)

            print(
                f"gesture={gesture_code:<6} expression={expression:<8} "
                f"phrase='{phrase}'  latency={latency_ms}ms  "
                f"(session total: {len(session_log)})"
            )
        except Exception as exc:
            print(f"[Speech ERROR] {exc}")
        finally:
            _speech_queue.task_done()


# Start as daemon so it exits automatically when the main process exits.
threading.Thread(target=_speech_worker, daemon=True, name="speech-worker").start()


def _enqueue_speech(gesture_code: str, phrase: str, expression: str) -> None:
    """
    Non-blocking enqueue.

    If the queue is full (one phrase already waiting), discard the waiting
    phrase and enqueue the new one — the latest gesture always wins.
    """
    item = (gesture_code, phrase, expression)
    try:
        _speech_queue.put_nowait(item)
    except queue.Full:
        # Drain the stale waiting item and replace with the new one.
        try:
            _speech_queue.get_nowait()
            _speech_queue.task_done()
        except queue.Empty:
            pass
        try:
            _speech_queue.put_nowait(item)
        except queue.Full:
            pass   # worker grabbed it between our drain and put — fine


# ---------------------------------------------------------------------------
# Gesture handler
# ---------------------------------------------------------------------------

def _handle_gesture(gesture_code: str) -> None:
    """
    Resolve phrase and enqueue for speech.

    Returns immediately — never blocks on TTS.
    """
    global last_gesture

    if gesture_code == last_gesture:
        return   # deduplicate: same gesture as last time
    last_gesture = gesture_code

    phrase = PHRASES.get(gesture_code, "I need help")

    # Capture expression snapshot at the time the gesture arrives.
    expression_snapshot = current_expression

    print(
        f"[Gesture] code={gesture_code}  phrase='{phrase}'  "
        f"expression={expression_snapshot}  → enqueued for speech"
    )

    _enqueue_speech(gesture_code, phrase, expression_snapshot)


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/gesture", methods=["POST"])
def receive_gesture():
    """
    Receives a gesture code from hand_gesture_camera.py.

    Returns "OK" in <1 ms — speech happens asynchronously.
    """
    try:
        code = request.json.get("gesture", "")
        if len(code) == 3 and all(c in "01" for c in code):
            _handle_gesture(code)
    except Exception as e:
        print(f"[ERROR] receive_gesture: {e}")
    return "OK"


@app.route("/expression", methods=["POST"])
def update_expression():
    """Receives expression label from mobile_vision.py."""
    global current_expression
    try:
        current_expression = request.json.get("expression", "NEUTRAL")
    except Exception as e:
        print(f"[ERROR] update_expression: {e}")
    return "OK"


@app.route("/status", methods=["GET"])
def status():
    """Returns current speech engine telemetry as JSON."""
    from flask import jsonify
    return jsonify(get_speech_status())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("[Silent Voice] Camera mode — no Arduino needed.")
    print(f"[Silent Voice] Flask listening on :{FLASK_PORT}")
    print("[Silent Voice] Speech worker thread: running")
    print("[Silent Voice] Waiting for gestures from hand_gesture_camera.py...\n")
    app.run(port=FLASK_PORT, host="0.0.0.0")


if __name__ == "__main__":
    main()
