import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  Mic,
  MicOff,
  PhoneOff,
  Radio,
  Square,
  Waves,
} from "lucide-react";
import { SlideOver } from "./SlideOver";
import {
  LiveVoiceClient,
  type VoiceState,
  type VoiceTuning,
} from "../lib/voiceClient";

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "Standby",
  listening: "Listening...",
  recording: "I hear you...",
  transcribing: "Transcribing...",
  thinking: "Thinking...",
  speaking: "Speaking...",
};

type LiveVoicePanelProps = {
  onClose: () => void;
  tuning: VoiceTuning;
  onTuningChange: (patch: Partial<VoiceTuning>) => void;
  onTranscript: (text: string) => void;
  onSentence: (text: string) => void;
  onResponseDone: (response: string, interrupted: boolean) => void;
};

export function LiveVoicePanel({
  onClose,
  tuning,
  onTuningChange,
  onTranscript,
  onSentence,
  onResponseDone,
}: LiveVoicePanelProps) {
  const clientRef = useRef<LiveVoiceClient | null>(null);

  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [state, setState] = useState<VoiceState>("idle");
  const [micLevel, setMicLevel] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      clientRef.current?.disconnect();
      clientRef.current = null;
    };
  }, []);

  const handleConnect = async () => {
    if (clientRef.current) {
      return;
    }

    setConnecting(true);
    setError(null);

    const client = new LiveVoiceClient();

    clientRef.current = client;

    try {
      await client.connect({
        onState: (nextState) => {
          setState(nextState);

          if (nextState === "listening") {
            setTranscript("");
            setReply("");
          }
        },
        onMicLevel: setMicLevel,
        onTranscript: (text) => {
          setTranscript(text);
          onTranscript(text);
        },
        onSentence: (text) => {
          setReply((previous) => previous + text);
          onSentence(text);
        },
        onResponseDone: (response, interrupted) => {
          setReply(response);
          onResponseDone(response, interrupted);
        },
        onError: (message) => setError(message),
        onClosed: () => {
          setConnected(false);
          setState("idle");
          setMicLevel(0);
        },
      });

      client.updateTuning(tuning);

      setConnected(true);
      setState("listening");
    } catch (connectError) {
      setError(
        connectError instanceof Error
          ? connectError.message
          : "Could not start voice mode.",
      );

      clientRef.current = null;
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = () => {
    clientRef.current?.disconnect();
    clientRef.current = null;

    setConnected(false);
    setState("idle");
    setMicLevel(0);
  };

  const toggleContinuous = () => {
    const next = !tuning.continuous;

    onTuningChange({ continuous: next });
    clientRef.current?.updateTuning({ continuous: next });
  };

  const orbActive =
    state === "speaking" || state === "recording" || state === "thinking";

  const levelPercent = Math.min(100, Math.round(micLevel * 700));

  return (
    <SlideOver
      title="Live voice"
      subtitle="Continuous conversation over WebSocket"
      onClose={onClose}
    >
      <div className="voice-stage">
        <div
          className={`voice-orb ${orbActive ? "active" : ""} ${
            state === "listening" ? "listening" : ""
          }`}
        >
          <div className="orb-ring ring-one" />
          <div className="orb-ring ring-two" />
          <div className="orb-ring ring-three" />
          <div className="orb">
            <AudioLines size={40} strokeWidth={1.3} />
          </div>
        </div>

        <div className="voice-state-row">
          <span className="voice-state-chip" data-state={state}>
            <Radio size={13} />
            {STATE_LABELS[state]}
          </span>
        </div>

        <div className="voice-meter">
          <span
            className="voice-meter-fill"
            style={{ width: `${levelPercent}%` }}
          />
        </div>

        {transcript && (
          <div className="voice-caption">
            <span className="voice-caption-label">YOU</span>
            <p>{transcript}</p>
          </div>
        )}

        {reply && (
          <div className="voice-caption jarvis">
            <span className="voice-caption-label">JARVIS</span>
            <p>{reply}</p>
          </div>
        )}

        {error && <div className="voice-error">{error}</div>}

        <div className="voice-controls">
          {!connected ? (
            <button
              className="voice-primary-button"
              onClick={() => void handleConnect()}
              disabled={connecting}
            >
              {connecting ? (
                <Square size={16} />
              ) : (
                <Mic size={17} />
              )}
              {connecting ? "Connecting..." : "Start conversation"}
            </button>
          ) : (
            <>
              <button
                className={`voice-primary-button ${
                  state === "speaking" ? "interrupting" : ""
                }`}
                onClick={() =>
                  clientRef.current?.sendInterrupt()
                }
                title="Interrupt Jarvis mid-sentence"
              >
                <Square size={15} />
                Interrupt
              </button>

              <button
                className={`voice-toggle ${tuning.continuous ? "enabled" : ""}`}
                onClick={toggleContinuous}
                title="Keep listening after each answer"
              >
                <Waves size={16} />
                Continuous {tuning.continuous ? "on" : "off"}
              </button>

              <button
                className="voice-danger-button"
                onClick={handleDisconnect}
              >
                <PhoneOff size={16} />
                End session
              </button>
            </>
          )}
        </div>

        <p className="voice-note">
          {connected
            ? tuning.continuous
              ? "Continuous mode: speak naturally, Jarvis listens for your voice and stops when you interrupt."
              : "Single-utterance mode: Jarvis listens once per turn. Toggle continuous to keep the mic open."
            : "Uses WebSocket streaming with on-device speech recognition and Piper TTS."}
        </p>

        {!connected && !connecting && (
          <p className="voice-permission-hint">
            <MicOff size={13} />
            Your browser will request microphone access.
          </p>
        )}
      </div>
    </SlideOver>
  );
}
