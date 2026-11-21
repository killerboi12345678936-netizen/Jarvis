
import tempfile
from pathlib import Path

from backend.core.config import settings

from backend.core.config import settings
from faster_whisper import WhisperModel


MODEL_SIZE = settings.whisper_model
DEVICE = settings.whisper_device
COMPUTE_TYPE = settings.whisper_compute_type

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


def preload_model():
    get_model()


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
