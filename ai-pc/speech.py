"""
Silent Voice — Speech Engine
============================

Provides a single public call:

    from speech import get_engine
    engine = get_engine()
    engine.speak("I need water")

Architecture
------------

    SpeechProvider          (abstract base)
         ├── SarvamProvider  (cloud TTS via Sarvam AI REST API)
         └── Pyttsx3Provider (offline TTS via pyttsx3 — always available)

    SpeechEngine            (orchestrator: tries configured provider,
                             auto-falls back to Pyttsx3Provider on any failure)

Configuration (.env — project root silent-voice/.env OR ai-pc/.env)
--------------------------------------------------------------------

    SPEECH_PROVIDER=sarvam          # "sarvam" or "pyttsx3"
    SARVAM_API_KEY=<your-key>
    SARVAM_LANGUAGE=en-IN           # BCP-47 target language (default en-IN)
    SARVAM_SPEAKER=shubh            # voice name  (default shubh)
    SARVAM_MODEL=bulbul:v3          # model name  (default bulbul:v3)
    SARVAM_TIMEOUT_SECONDS=8        # HTTP timeout in seconds (default 8)
    SPEECH_RATE=165                 # pyttsx3 words-per-minute (default 165)

All keys are optional — sensible defaults apply so the engine works
with zero configuration (pure offline mode).
"""

from __future__ import annotations

import base64
import io
import logging
import os
import pathlib
import socket
import tempfile
import time
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# .env loading  — FIX #1
# ---------------------------------------------------------------------------
# speech.py lives at:  silent-voice/ai-pc/speech.py
# .env lives at:       silent-voice/.env          (project root, one level up)
# A copy may also live at: silent-voice/ai-pc/.env (kept for convenience)
#
# Load order (first file found wins):
#   1. ai-pc/.env        — same dir as this script
#   2. silent-voice/.env — project root (one directory up)
#   3. python-dotenv CWD/parent walk — last-resort fallback
# ---------------------------------------------------------------------------
_ENV_LOADED: bool = False
try:
    from dotenv import load_dotenv

    _here        = pathlib.Path(__file__).resolve().parent          # ai-pc/
    _project_root = _here.parent                                    # silent-voice/

    _local_env   = _here        / ".env"   # ai-pc/.env
    _root_env    = _project_root / ".env"  # silent-voice/.env

    if _local_env.exists():
        _ENV_LOADED = load_dotenv(_local_env, override=True)
    elif _root_env.exists():
        _ENV_LOADED = load_dotenv(_root_env, override=True)
    else:
        _ENV_LOADED = load_dotenv(override=True)   # CWD / parent walk
except ImportError:
    pass  # python-dotenv not installed; rely on actual environment variables

import requests  # noqa: E402 — import after dotenv so proxies in env are visible

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

_DEFAULT_PROVIDER = "pyttsx3"
_DEFAULT_LANGUAGE = "en-IN"
_DEFAULT_SPEAKER  = "shubh"
_DEFAULT_MODEL    = "bulbul:v3"
_DEFAULT_TIMEOUT  = 8       # seconds
_DEFAULT_RATE     = 165     # pyttsx3 WPM

# A placeholder key string that ships in the sample .env.
# Treat this as "no key configured"
_PLACEHOLDER_KEY  = "your_sarvam_api_key_here"

# ---------------------------------------------------------------------------
# Telemetry dataclass
# ---------------------------------------------------------------------------

@dataclass
class SpeechTelemetry:
    configured_provider: str  = _DEFAULT_PROVIDER
    active_provider:     str  = _DEFAULT_PROVIDER
    status:              str  = "idle"
    latency_ms:          int  = 0
    fallback_count:      int  = 0
    internet_online:     bool = True
    last_phrase:         str  = ""
    last_failure_reason: str  = ""


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class SpeechProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def speak(self, text: str) -> int: ...

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Pyttsx3 provider  (always-available offline fallback)
# ---------------------------------------------------------------------------

class Pyttsx3Provider(SpeechProvider):

    def __init__(self, rate: int = _DEFAULT_RATE) -> None:
        self._rate = rate

    @property
    def name(self) -> str:
        return "Offline (pyttsx3)"

    def speak(self, text: str) -> int:
        import pyttsx3
        t0 = time.perf_counter()
        local_engine = pyttsx3.init()
        local_engine.setProperty("rate", self._rate)
        local_engine.say(text)
        local_engine.runAndWait()
        local_engine.stop()
        return int((time.perf_counter() - t0) * 1000)


# ---------------------------------------------------------------------------
# Sarvam AI provider  (cloud TTS)
# ---------------------------------------------------------------------------

class SarvamProvider(SpeechProvider):
    """
    Cloud TTS via Sarvam AI REST API.

    POST https://api.sarvam.ai/text-to-speech
    Header  : api-subscription-key: <SARVAM_API_KEY>
    Body    : { text, target_language_code, speaker, model, pace,
                speech_sample_rate }
    Response: { audios: ["<base64-wav>"], request_id }
    """

    def __init__(
        self,
        api_key:  str,
        language: str   = _DEFAULT_LANGUAGE,
        speaker:  str   = _DEFAULT_SPEAKER,
        model:    str   = _DEFAULT_MODEL,
        timeout:  int   = _DEFAULT_TIMEOUT,
        pace:     float = 1.0,
    ) -> None:
        if not api_key:
            raise ValueError("SARVAM_API_KEY is required for SarvamProvider")
        self._api_key  = api_key
        self._language = language
        self._speaker  = speaker
        self._model    = model
        self._timeout  = timeout
        self._pace     = pace
        self._session  = requests.Session()
        self._session.headers.update({
            "api-subscription-key": self._api_key,
            "Content-Type":         "application/json",
        })

    @property
    def name(self) -> str:
        return "Sarvam AI"

    def speak(self, text: str) -> int:
        # FIX #3 — print before every Sarvam request
        print("Attempting Sarvam TTS...")

        t0 = time.perf_counter()

        payload: dict = {
            "text":                 text,
            "target_language_code": self._language,
            "speaker":              self._speaker,
            "model":                self._model,
            "pace":                 self._pace,
            "speech_sample_rate":   22050,
        }

        # enable_preprocessing not supported on bulbul:v3
        if not self._model.startswith("bulbul:v3"):
            payload["enable_preprocessing"] = True

        response = self._session.post(
            SARVAM_TTS_URL,
            json=payload,
            timeout=self._timeout,
        )
        response.raise_for_status()

        data   = response.json()
        audios = data.get("audios")
        if not audios or not isinstance(audios, list) or not audios[0]:
            raise ValueError(
                f"Sarvam response missing audio data. "
                f"request_id={data.get('request_id')}"
            )

        wav_bytes = base64.b64decode(audios[0])
        api_latency_ms = int((time.perf_counter() - t0) * 1000)
        print(f"Sarvam TTS: API responded in {api_latency_ms} ms — audio received ({len(wav_bytes)} bytes)")

        self._play_wav_bytes(wav_bytes)
        return int((time.perf_counter() - t0) * 1000)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _play_wav_bytes(wav_bytes: bytes) -> None:
        # Strategy 1: pyaudio
        try:
            import pyaudio
            with wave.open(io.BytesIO(wav_bytes)) as wf:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pa.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True,
                )
                try:
                    chunk = 1024
                    data = wf.readframes(chunk)
                    while data:
                        stream.write(data)
                        data = wf.readframes(chunk)
                finally:
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
            return
        except ImportError:
            logger.debug("pyaudio not available; trying winsound / aplay")
        except Exception as exc:
            logger.warning("pyaudio playback failed (%s); trying fallback", exc)

        # Strategy 2/3: temp file + system player
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            import sys
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(tmp_path, winsound.SND_FILENAME)
            else:
                import subprocess
                subprocess.run(["aplay", tmp_path], check=True, capture_output=True)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def close(self) -> None:
        self._session.close()


# ---------------------------------------------------------------------------
# Internet connectivity probe
# ---------------------------------------------------------------------------

def _is_internet_available(host: str = "8.8.8.8", port: int = 53,
                            timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Speech Engine
# ---------------------------------------------------------------------------

class SpeechEngine:
    """
    Orchestrates provider selection, automatic fallback, telemetry, and
    console output.

    Usage
    -----
        engine = SpeechEngine()
        engine.speak("I need water")
    """

    def __init__(self) -> None:
        self._telemetry = SpeechTelemetry()
        self._offline   = Pyttsx3Provider(
            rate=int(os.getenv("SPEECH_RATE", str(_DEFAULT_RATE)))
        )

        configured = os.getenv("SPEECH_PROVIDER", _DEFAULT_PROVIDER).lower().strip()
        self._telemetry.configured_provider = configured
        self._telemetry.active_provider     = configured

        self._primary: Optional[SpeechProvider] = None
        self._consecutive_failures: int          = 0
        self._max_consecutive_failures: int      = 3
        self._sarvam_permanently_disabled: bool  = False

        # --- FIX #2: resolve key and detect placeholder --------------------
        raw_key = os.getenv("SARVAM_API_KEY", "").strip()
        api_key = raw_key if raw_key and raw_key != _PLACEHOLDER_KEY else ""

        # --- FIX #2: startup banner ----------------------------------------
        key_present    = "YES" if api_key else "NO"
        sarvam_enabled = "YES" if (configured == "sarvam" and api_key) else "NO"

        print("=" * 40)
        print("Speech Engine")
        print("=" * 40)
        print(f"  Configured Provider : {configured}")
        print(f"  Environment Loaded  : {'YES' if _ENV_LOADED else 'NO'}")
        print(f"  API Key Present     : {key_present}")
        print(f"  Sarvam Enabled      : {sarvam_enabled}")
        print("=" * 40)

        if configured == "sarvam":
            if not api_key:
                _reason = (
                    "SARVAM_API_KEY is not set"
                    if not raw_key
                    else f"SARVAM_API_KEY is still the placeholder value ({_PLACEHOLDER_KEY!r})"
                )
                print(f"  WARNING: {_reason}")
                print("  Falling back to Offline pyttsx3")
                print(f"  Reason: {_reason}")
                self._sarvam_permanently_disabled = True
                self._telemetry.active_provider   = "pyttsx3"
            else:
                try:
                    self._primary = SarvamProvider(
                        api_key  = api_key,
                        language = os.getenv("SARVAM_LANGUAGE", _DEFAULT_LANGUAGE),
                        speaker  = os.getenv("SARVAM_SPEAKER",  _DEFAULT_SPEAKER),
                        model    = os.getenv("SARVAM_MODEL",    _DEFAULT_MODEL),
                        timeout  = int(os.getenv("SARVAM_TIMEOUT_SECONDS",
                                                 str(_DEFAULT_TIMEOUT))),
                    )
                    print("  SarvamProvider initialised successfully.")
                except Exception as exc:
                    print(f"  ERROR: SarvamProvider init failed: {exc}")
                    print("  Falling back to Offline pyttsx3")
                    print(f"  Reason: {exc}")
                    self._sarvam_permanently_disabled = True
                    self._telemetry.active_provider   = "pyttsx3"

        logger.info(
            "SpeechEngine ready | configured=%s active=%s env_loaded=%s api_key=%s",
            self._telemetry.configured_provider,
            self._telemetry.active_provider,
            _ENV_LOADED,
            key_present,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str) -> None:
        self._telemetry.last_phrase     = text
        self._telemetry.internet_online = _is_internet_available()

        sarvam_ready = (
            self._primary is not None
            and not self._sarvam_permanently_disabled
        )

        if sarvam_ready:
            self._speak_with_primary(text)
        else:
            self._speak_offline(text, reason=None)

    def get_speech_status(self) -> dict:
        t = self._telemetry
        return {
            "configured_provider": t.configured_provider,
            "active_provider":     t.active_provider,
            "status":              t.status,
            "latency_ms":          t.latency_ms,
            "fallback_count":      t.fallback_count,
            "internet_online":     t.internet_online,
            "last_phrase":         t.last_phrase,
            "last_error":          t.last_failure_reason,
        }

    def close(self) -> None:
        if self._primary:
            self._primary.close()
        self._offline.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _speak_with_primary(self, text: str) -> None:
        """Attempt Sarvam; on any exception expose the full reason and fall back."""
        try:
            ms = self._primary.speak(text)
            self._consecutive_failures      = 0
            self._telemetry.latency_ms      = ms
            self._telemetry.status          = "ok"
            self._telemetry.active_provider = "sarvam"
            self._print_speech_banner(
                configured=self._telemetry.configured_provider,
                active=self._primary.name,
                latency_ms=ms,
                phrase=text,
            )

        # FIX #4 & #7 — never swallow exceptions; always print the full reason
        except requests.exceptions.Timeout as exc:
            reason = f"Timeout — request exceeded {exc}"
            self._handle_fallback(text, reason)

        except requests.exceptions.ConnectionError as exc:
            reason = f"ConnectionError — {exc}"
            self._handle_fallback(text, reason)

        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "?"
            try:
                body = exc.response.text[:500]
            except Exception:
                body = "(could not read response body)"
            reason = f"HTTP {status_code} — {body}"
            self._handle_fallback(text, reason)

        except requests.exceptions.RequestException as exc:
            reason = f"Network Error ({type(exc).__name__}): {exc}"
            self._handle_fallback(text, reason)

        except ValueError as exc:
            reason = f"Invalid Response: {exc}"
            self._handle_fallback(text, reason)

        except Exception as exc:
            reason = f"Unexpected Error ({type(exc).__name__}): {exc}"
            self._handle_fallback(text, reason)

    def _handle_fallback(self, text: str, reason: str) -> None:
        self._consecutive_failures         += 1
        self._telemetry.fallback_count     += 1
        self._telemetry.last_failure_reason = reason
        self._telemetry.status              = "fallback"
        self._telemetry.active_provider     = "pyttsx3"

        # FIX #5 — always print full reason before speaking offline
        print("Falling back to Offline pyttsx3")
        print(f"Reason: {reason}")
        logger.warning("Sarvam TTS failed — falling back. Reason: %s", reason)

        if self._consecutive_failures >= self._max_consecutive_failures:
            self._sarvam_permanently_disabled = True
            msg = (
                f"Sarvam TTS failed {self._consecutive_failures} times in a row — "
                "permanently disabled for this session."
            )
            print(f"WARNING: {msg}")
            logger.warning(msg)

        self._speak_offline(text, reason=reason)

    def _speak_offline(self, text: str, reason: Optional[str]) -> None:
        try:
            ms = self._offline.speak(text)
            self._telemetry.latency_ms = ms
            if reason is not None:
                self._print_fallback_banner(reason=reason)
                if not self._sarvam_permanently_disabled and self._primary is not None:
                    self._telemetry.active_provider = "sarvam"
            else:
                self._telemetry.status = "ok"
                self._print_speech_banner(
                    configured=self._telemetry.configured_provider,
                    active=self._offline.name,
                    latency_ms=ms,
                    phrase=text,
                )
        except Exception as exc:
            self._telemetry.status = "error"
            logger.error("pyttsx3 fallback also failed: %s", exc)
            print(f"[Speech ERROR] pyttsx3 also failed for '{text}': {exc}")

    @staticmethod
    def _print_speech_banner(configured, active, latency_ms, phrase):
        sep = "=" * 40
        configured_label = "Sarvam AI" if configured == "sarvam" else "Offline (pyttsx3)"
        print(sep)
        print("Speech Engine")
        print(f"  Configured Provider : {configured_label}")
        print(f"  Active Provider     : {active}")
        print(f"  Latency             : {latency_ms} ms")
        print(f"  Phrase              : {phrase}")
        print(sep)

    def _print_fallback_banner(self, reason: str):
        t = self._telemetry
        configured_label = (
            "Sarvam AI" if t.configured_provider == "sarvam" else "Offline (pyttsx3)"
        )
        sep = "=" * 40
        print(sep)
        print("Speech Engine")
        print(f"  Configured Provider : {configured_label}")
        print(f"  Active Provider     : {self._offline.name}")
        print(f"  Reason              : {reason}")
        print(f"  Fallback Count      : {t.fallback_count}")
        print(sep)


# ---------------------------------------------------------------------------
# Module-level singleton factory
# ---------------------------------------------------------------------------

_engine_instance: Optional[SpeechEngine] = None


def get_engine() -> SpeechEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SpeechEngine()
    return _engine_instance


def get_speech_status() -> dict:
    return get_engine().get_speech_status()


# ---------------------------------------------------------------------------
# FIX #6 — Standalone Sarvam API verification function
# ---------------------------------------------------------------------------

def test_sarvam(text: str = "Hello from Sarvam AI") -> None:
    """
    Standalone test for the Sarvam TTS API.

    Does NOT require the rest of the application.
    Reads SARVAM_API_KEY directly from the environment (or .env) and
    makes one real API call, printing the full request/response details.

    Usage (from terminal, inside ai-pc/):
        python -c "from speech import test_sarvam; test_sarvam()"
    """
    import sys

    print("=" * 40)
    print("Sarvam TTS — API Test")
    print("=" * 40)

    # Resolve .env — use override=True so we always get the file's current values
    try:
        from dotenv import load_dotenv as _load
        _h = pathlib.Path(__file__).resolve().parent
        _r = _h.parent
        if (_h / ".env").exists():
            _load(_h / ".env", override=True)
        elif (_r / ".env").exists():
            _load(_r / ".env", override=True)
        else:
            _load(override=True)
    except ImportError:
        pass

    raw_key = os.getenv("SARVAM_API_KEY", "").strip()
    api_key = raw_key if raw_key and raw_key != _PLACEHOLDER_KEY else ""

    print(f"  Text            : {text!r}")
    print(f"  API Key Present : {'YES' if api_key else 'NO'}")
    if not api_key:
        print()
        print("  FAILED: Set a real SARVAM_API_KEY in .env and try again.")
        print("=" * 40)
        return

    language = os.getenv("SARVAM_LANGUAGE", _DEFAULT_LANGUAGE)
    speaker  = os.getenv("SARVAM_SPEAKER",  _DEFAULT_SPEAKER)
    model    = os.getenv("SARVAM_MODEL",     _DEFAULT_MODEL)
    timeout  = int(os.getenv("SARVAM_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT)))

    payload = {
        "text":                 text,
        "target_language_code": language,
        "speaker":              speaker,
        "model":                model,
        "pace":                 1.0,
        "speech_sample_rate":   22050,
    }
    if not model.startswith("bulbul:v3"):
        payload["enable_preprocessing"] = True

    headers = {
        "api-subscription-key": api_key,
        "Content-Type":         "application/json",
    }

    print(f"  Endpoint        : POST {SARVAM_TTS_URL}")
    print(f"  Model           : {model}")
    print(f"  Speaker         : {speaker}")
    print(f"  Language        : {language}")
    print()
    print("  Sending request...")

    try:
        resp = requests.post(SARVAM_TTS_URL, json=payload,
                             headers=headers, timeout=timeout)
        print(f"  Response Status : HTTP {resp.status_code}")

        if resp.status_code != 200:
            print(f"  Response Body   : {resp.text[:800]}")
            print()
            print("  FAILED: Non-200 response from Sarvam.")
            print("=" * 40)
            return

        data   = resp.json()
        audios = data.get("audios")

        if not audios or not isinstance(audios, list) or not audios[0]:
            print(f"  ERROR: No audio in response. Full body: {resp.text[:400]}")
            print("=" * 40)
            return

        wav_bytes = base64.b64decode(audios[0])
        print(f"  Audio Received  : YES ({len(wav_bytes)} bytes)")
        print(f"  Request ID      : {data.get('request_id', 'N/A')}")
        print()
        print("  Playing audio...")

        SarvamProvider._play_wav_bytes(wav_bytes)

        print("  Playback complete.")
        print()
        print("  RESULT: Sarvam TTS is working correctly.")

    except requests.exceptions.Timeout:
        print(f"  FAILED: Request timed out after {timeout}s.")
    except requests.exceptions.ConnectionError as exc:
        print(f"  FAILED: ConnectionError — {exc}")
    except requests.exceptions.HTTPError as exc:
        print(f"  FAILED: HTTP error — {exc}")
    except Exception as exc:
        print(f"  FAILED: Unexpected error ({type(exc).__name__}): {exc}")

    print("=" * 40)


# ---------------------------------------------------------------------------
# CLI entry-point:  python speech.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    test_sarvam()
