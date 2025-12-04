# interrupt_handler.py
# Place in your repo, e.g. livekit_agents/utils/interrupt_handler.py

import threading
import time
from typing import Callable, List, Optional, Dict

class Transcript:
    def __init__(self, text: str, is_final: bool = False, timestamp: Optional[float] = None):
        self.text = text
        self.is_final = is_final
        self.timestamp = timestamp or time.time()

class InterruptHandlerConfig:
    def __init__(
        self,
        soft_words: Optional[List[str]] = None,
        hard_words: Optional[List[str]] = None,
        validation_window_ms: int = 225
    ):
        self.soft_words = [s.lower() for s in (soft_words or [
            'yeah','ok','hmm','right','uh-huh','mhm','uh huh'
        ])]
        self.hard_words = [h.lower() for h in (hard_words or [
            'wait','stop','no','hold on','pause','cancel','hang on','stop that','stop it'
        ])]
        self.validation_window_ms = validation_window_ms

class InterruptHandler:
    """
    Handles VAD -> STT race by validating transcripts for short soft-words.
    Usage:
      - call on_vad_user_started() when VAD says user started speaking
      - call on_stt_transcript(Transcript(...)) when STT partials/finals arrive
      - supply callbacks for stopping agent playback, processing normally, etc.
    """

    def __init__(
        self,
        config: InterruptHandlerConfig,
        stop_agent_immediately: Callable[[], None],
        ignore_user_speech: Optional[Callable[[], None]],
        process_user_speech_normally: Callable[[Transcript], None],
        get_agent_speaking_state: Callable[[], bool],
        logger: Optional[Callable[[str], None]] = None
    ):
        self.cfg = config
        self.stop_agent_immediately = stop_agent_immediately
        self.ignore_user_speech = ignore_user_speech
        self.process_user_speech_normally = process_user_speech_normally
        self.get_agent_speaking_state = get_agent_speaking_state
        self.logger = logger or (lambda x: None)

        self._pending_vad = False
        self._transcript_buffer: List[Transcript] = []
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def on_vad_user_started(self) -> None:
        with self._lock:
            self.logger(f"[{self._now()}] VAD user-start detected.")
            # If agent not speaking => we let normal processing happen (but we still await STT)
            self._pending_vad = True
            self._transcript_buffer = []
            self._start_timer()

    def on_stt_transcript(self, transcript: Transcript) -> None:
        with self._lock:
            if not self._pending_vad:
                # No VAD pending — process normally (agent silent or no race)
                self.logger(f"[{self._now()}] STT arrived with no VAD pending: '{transcript.text}'")
                self.process_user_speech_normally(transcript)
                return

            # Accumulate transcript fragments
            self._transcript_buffer.append(transcript)
            combined = " ".join(t.text for t in self._transcript_buffer).lower().strip()
            norm = self._normalize(combined)
            self.logger(f"[{self._now()}] STT during pending VAD: '{combined}' -> norm='{norm}'")

            # Check for any hard words (phrase match)
            for hard in self.cfg.hard_words:
                if hard in norm:
                    self._clear_pending()
                    self.logger(f"[{self._now()}] Hard word '{hard}' detected -> interrupting immediately.")
                    self.stop_agent_immediately()
                    return

            # If agent is speaking, check if the transcript is only soft words
            if self.get_agent_speaking_state():
                tokens = norm.split()
                # consider it soft if it's short and all tokens are in soft list or tiny fillers
                only_soft = all((t in self.cfg.soft_words) or (len(t) <= 2) for t in tokens)
                if only_soft:
                    self._clear_pending()
                    self.logger(f"[{self._now()}] Only soft/backchannel detected -> IGNORING while speaking.")
                    if self.ignore_user_speech:
                        self.ignore_user_speech()
                    return
                else:
                    # contains other words -> treat as interrupt
                    self._clear_pending()
                    self.logger(f"[{self._now()}] Non-soft content while speaking -> INTERRUPT.")
                    self.stop_agent_immediately()
                    return
            else:
                # Agent not speaking and VAD pending -> process transcript normally
                self._clear_pending()
                self.logger(f"[{self._now()}] Agent silent -> processing user speech normally.")
                self.process_user_speech_normally(Transcript(combined, transcript.is_final))
                return

    def agent_started_speaking(self) -> None:
        with self._lock:
            # reset any pending VAD (we are starting to talk)
            self._clear_pending()
            self.logger(f"[{self._now()}] Agent started speaking - state reset.")

    def agent_stopped_speaking(self) -> None:
        with self._lock:
            self._clear_pending()
            self.logger(f"[{self._now()}] Agent stopped speaking - state reset.")

    def _start_timer(self):
        # Cancel existing timer
        if self._timer:
            self._timer.cancel()
            self._timer = None
        # Launch a timer to avoid indefinite waiting for STT
        ms = max(50, int(self.cfg.validation_window_ms))
        self._timer = threading.Timer(ms / 1000.0, self._on_timer_expired)
        self._timer.daemon = True
        self._timer.start()
        self.logger(f"[{self._now()}] Validation timer started ({ms} ms).")

    def _on_timer_expired(self):
        with self._lock:
            if not self._pending_vad:
                return
            self.logger(f"[{self._now()}] Validation timer expired.")
            # Conservative default: if agent is speaking -> ignore
            if self.get_agent_speaking_state():
                self.logger(f"[{self._now()}] Timeout and agent was speaking -> IGNORE user speech.")
                if self.ignore_user_speech:
                    self.ignore_user_speech()
                self._clear_pending()
                return
            else:
                # No STT arrived and agent silent -> nothing to process
                self.logger(f"[{self._now()}] Timeout and agent silent -> no STT -> nothing to do.")
                self._clear_pending()
                return

    def _clear_pending(self):
        self._pending_vad = False
        self._transcript_buffer = []
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _normalize(self, s: str) -> str:
        # simple normalization: remove punctuation (except apostrophes), normalize whitespace
        import re
        s2 = re.sub(r"[^\w\s'-]", ' ', s)
        return " ".join(s2.split())

    def _now(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime())
