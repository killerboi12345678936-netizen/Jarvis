import { Mic, Send, Square } from "lucide-react";

type ComposerProps = {
  input: string;
  loading: boolean;
  recording: boolean;
  speaking: boolean;
  connected: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onStopSpeaking: () => void;
  onToggleRecording: () => void;
};

export function Composer({
  input,
  loading,
  recording,
  speaking,
  connected,
  onInputChange,
  onSend,
  onStopSpeaking,
  onToggleRecording,
}: ComposerProps) {
  return (
    <footer className="composer-area">
      <div className="composer">
        <input
          id="jarvis-chat-input"
          name="message"
          type="text"
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          placeholder="Message Jarvis..."
          disabled={loading || recording}
        />

        <div className="composer-actions">
          {speaking && (
            <button
              className="icon-button"
              onClick={onStopSpeaking}
              title="Stop speaking"
            >
              <Square size={16} />
            </button>
          )}

          <button
            className={`icon-button ${recording ? "recording" : ""}`}
            onClick={onToggleRecording}
            disabled={!connected || loading}
            title={recording ? "Stop recording" : "Start voice input"}
          >
            {recording ? <Square size={17} /> : <Mic size={19} />}
          </button>

          <button
            className="send-button"
            onClick={onSend}
            disabled={!input.trim() || loading || !connected}
            title="Send message"
          >
            <Send size={18} />
          </button>
        </div>
      </div>

      <div className="composer-caption">
        <span>JARVIS AI · V1.0</span>
        <span>
          {recording
            ? "Recording · press stop when finished"
            : "Text and voice interface"}
        </span>
      </div>
    </footer>
  );
}
