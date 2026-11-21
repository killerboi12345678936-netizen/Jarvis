import { Mic, Volume2 } from "lucide-react";
import { SlideOver } from "./SlideOver";
import type { VoiceTuning } from "../lib/voiceClient";

type SettingsPanelProps = {
  onClose: () => void;
  tuning: VoiceTuning;
  onTuningChange: (patch: Partial<VoiceTuning>) => void;
};

export function SettingsPanel({
  onClose,
  tuning,
  onTuningChange,
}: SettingsPanelProps) {
  return (
    <SlideOver
      title="Settings"
      subtitle="Voice detection tuning"
      onClose={onClose}
    >
      <div className="settings-section">
        <span className="digest-label">
          <Mic size={13} />
          SPEECH DETECTION
        </span>

        <label className="slider-row">
          <span className="slider-name">Speech threshold</span>
          <input
            type="range"
            min={0.005}
            max={0.1}
            step={0.005}
            value={tuning.speechThreshold}
            onChange={(event) =>
              onTuningChange({
                speechThreshold: Number(event.target.value),
              })
            }
          />
          <span className="slider-value">
            {tuning.speechThreshold.toFixed(3)}
          </span>
          <span className="slider-hint">
            Lower catches quieter speech, higher ignores background noise.
          </span>
        </label>

        <label className="slider-row">
          <span className="slider-name">Silence before reply</span>
          <input
            type="range"
            min={400}
            max={2000}
            step={100}
            value={tuning.silenceMs}
            onChange={(event) =>
              onTuningChange({ silenceMs: Number(event.target.value) })
            }
          />
          <span className="slider-value">{tuning.silenceMs} ms</span>
          <span className="slider-hint">
            How long you may pause before Jarvis starts answering.
          </span>
        </label>

        <label className="slider-row">
          <span className="slider-name">Minimum speech</span>
          <input
            type="range"
            min={100}
            max={1000}
            step={50}
            value={tuning.minSpeechMs}
            onChange={(event) =>
              onTuningChange({ minSpeechMs: Number(event.target.value) })
            }
          />
          <span className="slider-value">{tuning.minSpeechMs} ms</span>
          <span className="slider-hint">
            Shorter noises (coughs, clicks) are ignored.
          </span>
        </label>

        <label className="slider-row">
          <span className="slider-name">Barge-in threshold</span>
          <input
            type="range"
            min={0.01}
            max={0.1}
            step={0.005}
            value={tuning.bargeInThreshold}
            onChange={(event) =>
              onTuningChange({
                bargeInThreshold: Number(event.target.value),
              })
            }
          />
          <span className="slider-value">
            {tuning.bargeInThreshold.toFixed(3)}
          </span>
          <span className="slider-hint">
            How loudly you must speak to interrupt Jarvis while it talks.
          </span>
        </label>
      </div>

      <div className="settings-section">
        <span className="digest-label">
          <Volume2 size={13} />
          TEXT-TO-SPEECH
        </span>
        <p className="panel-note">
          Responses are spoken sentence-by-sentence with Piper while they
          stream in. Toggle voice in the toolbar above, or use the read-aloud
          button on any message.
        </p>
      </div>

      <p className="panel-note">
        Changes apply immediately to the live voice session. Backend defaults
        can be set through environment variables — see .env.example.
      </p>
    </SlideOver>
  );
}
