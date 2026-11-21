
import numpy as np
import pytest

from backend.voice.stream import INTERRUPT, VoiceSession


SAMPLE_RATE = 16000

FRAME_MS = 100


def make_frame(ms=FRAME_MS, amplitude=0.0):
    samples = int(SAMPLE_RATE * ms / 1000)

    pcm = np.full(samples, amplitude * 32767, dtype=np.float32)

    return pcm.astype(np.int16).tobytes()


def feed(session, frames):
    results = []

    for frame in frames:
        outcome = session.process_audio(frame)

        if outcome is not None:
            results.append(outcome)

    return results


@pytest.fixture()
def session():
    voice = VoiceSession()

    voice.silence_ms = 250
    voice.min_speech_ms = 150

    return voice


def test_silence_keeps_session_idle(session):
    outcomes = feed(session, [make_frame() for _ in range(5)])

    assert outcomes == []
    assert session.state == "idle"


def test_utterance_completes_with_pre_roll(session):
    pre_silence = make_frame()

    outcomes = feed(
        session,
        [pre_silence, make_frame(amplitude=0.3), make_frame(amplitude=0.3)]
        + [make_frame() for _ in range(4)],
    )

    assert len(outcomes) == 1

    utterance = outcomes[0]

    assert session.state == "transcribing"
    assert utterance.startswith(pre_silence)

    samples = len(utterance) // 2
    assert samples >= int(SAMPLE_RATE * 500 / 1000)


def test_short_noise_is_discarded(session):
    outcomes = feed(
        session,
        [make_frame(amplitude=0.3)]
        + [make_frame() for _ in range(3)],
    )

    assert outcomes == []
    assert session.state == "listening"


def test_barge_in_needs_consecutive_loud_frames(session):
    session.state = "thinking"

    assert session.process_audio(make_frame(amplitude=0.3)) is None

    assert session.process_audio(make_frame()) is None

    assert session.barge_in_count == 0

    assert session.process_audio(make_frame(amplitude=0.3)) is None

    assert session.process_audio(make_frame(amplitude=0.3)) == INTERRUPT


def test_quiet_frame_resets_barge_in_counter(session):
    session.state = "speaking"

    assert session.process_audio(make_frame(amplitude=0.3)) is None

    assert session.process_audio(make_frame()) is None

    assert session.process_audio(make_frame(amplitude=0.3)) is None

    assert session.barge_in_count == 1


def test_empty_chunk_is_safe(session):
    assert session.process_audio(b"") is None

    assert session.state == "idle"
