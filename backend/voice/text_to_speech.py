
import asyncio
import os
import shutil
import subprocess
import uuid

from pathlib import Path
from dotenv import load_dotenv


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

VOICE_DIR = PROJECT_ROOT / "data" / "voice"
VOICE_DIR.mkdir(parents=True, exist_ok=True)

PIPER_EXECUTABLE = os.getenv("PIPER_EXECUTABLE", "piper")

PIPER_MODEL = os.getenv(
    "PIPER_MODEL",
    "data/voice/en_US-lessac-medium.onnx"
)


# --------------------------------------------------
# PIPER EXECUTION
# --------------------------------------------------

def _find_piper_executable():

    located = shutil.which(PIPER_EXECUTABLE)

    if located:
        return located

    # uvicorn is often started with .venv\Scripts\python.exe without
    # activating the venv, which leaves piper off the PATH.
    candidates = (
        PROJECT_ROOT / ".venv" / "Scripts" / f"{PIPER_EXECUTABLE}.exe",
        PROJECT_ROOT / ".venv" / "Scripts" / PIPER_EXECUTABLE,
        PROJECT_ROOT / ".venv" / "bin" / PIPER_EXECUTABLE,
    )

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return None


def _generate_audio(text: str) -> Path:

    executable = _find_piper_executable()

    if not executable:
        raise RuntimeError(
            f"Piper executable not found: {PIPER_EXECUTABLE}"
        )

    model_path = Path(PIPER_MODEL).expanduser()

    if not model_path.is_absolute():
        model_path = PROJECT_ROOT / model_path

    model_path = model_path.resolve()

    if not model_path.is_file():
        raise RuntimeError(
            f"Piper voice model not found: {model_path}. It is not "
            "bundled with the repository; download en_US-lessac-medium"
            ".onnx and en_US-lessac-medium.onnx.json from "
            "https://huggingface.co/rhasspy/piper-voices into "
            "data/voice/ or point PIPER_MODEL in .env at your own "
            "Piper .onnx voice."
        )

    output_path = VOICE_DIR / f"{uuid.uuid4().hex}.wav"

    command = [
        executable,
        "--model",
        str(model_path),
        "--output_file",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            command,
            input=(text.strip() + "\n").encode("utf-8"),
            capture_output=True,
            cwd=str(PROJECT_ROOT),
            timeout=120,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)

        raise RuntimeError(
            "Piper speech generation timed out after 120 seconds."
        ) from exc

    except OSError as exc:
        output_path.unlink(missing_ok=True)

        raise RuntimeError(
            f"Could not execute Piper: {exc}"
        ) from exc

    if result.returncode != 0:
        output_path.unlink(missing_ok=True)

        stderr = result.stderr.decode(
            "utf-8", errors="replace"
        ).strip()

        stdout = result.stdout.decode(
            "utf-8", errors="replace"
        ).strip()

        diagnostic = (
            stderr
            or stdout
            or f"No diagnostic output. Exit code: {result.returncode}"
        )

        raise RuntimeError(
            f"Piper failed: {diagnostic[:1500]}"
        )

    if not output_path.is_file():
        raise RuntimeError(
            "Piper did not create an audio file."
        )

    if output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)

        raise RuntimeError(
            "Piper generated an empty audio file."
        )

    return output_path


# --------------------------------------------------
# ASYNC PUBLIC FUNCTIONS
# --------------------------------------------------

async def synthesize_speech(text: str) -> Path:

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text cannot be empty.")

    if len(text) > 5000:
        raise ValueError(
            "Text exceeds the 5000 character limit."
        )

    return await asyncio.to_thread(
        _generate_audio,
        text
    )


async def synthesize_sentence(text: str) -> Path:
    """
    Generate one sentence as a separate WAV file.
    Intended for progressive speech playback.
    """

    if not isinstance(text, str) or not text.strip():
        raise ValueError("Sentence cannot be empty.")

    if len(text) > 1000:
        raise ValueError(
            "Sentence exceeds the 1000 character limit."
        )

    return await asyncio.to_thread(
        _generate_audio,
        text
    )
