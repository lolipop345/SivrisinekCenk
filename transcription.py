from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

log = logging.getLogger("transcription")


class Transcriber:
    """faster-whisper wrapper with lazy model load and async-safe transcribe.

    Model download (Systran/faster-whisper-<size>) happens on first
    transcribe call, not at construction — bot startup stays fast and
    users who never send audio never pay the cost.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._language = language
        self._model = None
        self._init_lock = asyncio.Lock()

    async def _ensure_init(self) -> None:
        if self._model is not None:
            return
        async with self._init_lock:
            if self._model is not None:
                return
            from faster_whisper import WhisperModel
            loop = asyncio.get_running_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    self._model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                ),
            )
            log.info(
                "whisper-%s loaded (device=%s, compute=%s)",
                self._model_size,
                self._device,
                self._compute_type,
            )

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not audio_bytes:
            return ""
        await self._ensure_init()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._do_transcribe, audio_bytes)

    def _do_transcribe(self, audio_bytes: bytes) -> str:
        segments, _info = self._model.transcribe(
            io.BytesIO(audio_bytes),
            beam_size=1,
            language=self._language,
            vad_filter=True,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
