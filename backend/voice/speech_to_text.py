
import os
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel


MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_model = None


def get_model():
    global _model

    if _model is None:
        _model = WhisperModel(
            MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE,
        )

    return _model


def transcribe_audio(audio_bytes: bytes, suffix=".webm"):
    if not audio_bytes:
        raise ValueError("Audio recording is empty.")

    if len(audio_bytes) > 20 * 1024 * 1024:
        raise ValueError("Audio recording exceeds the 20 MB limit.")

    allowed_suffixes = {".webm", ".wav", ".mp3", ".m4a", ".ogg"}

    if suffix not in allowed_suffixes:
        raise ValueError("Unsupported audio format.")

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            delete=False,
        ) as temp:
            temp.write(audio_bytes)
            temp_path = temp.name

        model = get_model()

        segments, info = model.transcribe(
            temp_path,
            beam_size=3,
            vad_filter=True,
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability,
        }

    finally:
        if temp_path and Path(temp_path).exists():
            Path(temp_path).unlink()
