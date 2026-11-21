import { Mic, Volume2, VolumeX, Waves } from "lucide-react";

type ProviderInfo = {
  configured: boolean;
  online: boolean;
  model: string;
};

type ProviderToolbarProps = {
  provider: string;
  model: string;
  providers: Record<string, ProviderInfo>;
  models: string[];
  voiceEnabled: boolean;
  onProviderChange: (provider: string) => void;
  onModelChange: (model: string) => void;
  onToggleVoice: () => void;
  onOpenLiveVoice: () => void;
};

export function ProviderToolbar({
  provider,
  model,
  providers,
  models,
  voiceEnabled,
  onProviderChange,
  onModelChange,
  onToggleVoice,
  onOpenLiveVoice,
}: ProviderToolbarProps) {
  return (
    <div className="provider-toolbar">
      <label>
        AI PROVIDER
        <select
          value={provider}
          onChange={(event) => onProviderChange(event.target.value)}
        >
          {Object.entries(providers).map(([name, info]) => (
            <option
              key={name}
              value={name}
              disabled={!info.configured || !info.online}
            >
              {name.toUpperCase()}
              {!info.online ? " (offline)" : ""}
            </option>
          ))}
        </select>
      </label>

      {provider === "ollama" && (
        <label>
          MODEL
          <select
            value={model}
            onChange={(event) => onModelChange(event.target.value)}
          >
            {models.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}

      <button
        className={`voice-toggle ${voiceEnabled ? "enabled" : ""}`}
        onClick={onToggleVoice}
        title="Toggle voice responses"
      >
        {voiceEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
        Voice {voiceEnabled ? "on" : "off"}
      </button>

      <button
        className="voice-toggle live"
        onClick={onOpenLiveVoice}
        title="Open live voice mode (continuous conversation)"
      >
        <Waves size={17} />
        Live voice
      </button>

      <span className="toolbar-hint">
        <Mic size={13} />
        Push the mic for quick dictation, or open live voice for a
        hands-free conversation.
      </span>
    </div>
  );
}
