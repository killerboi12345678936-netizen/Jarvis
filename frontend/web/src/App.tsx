
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AudioLines,
  ChevronDown,
  CircleHelp,
  Command,
  Cpu,
  Menu,
  MessageSquare,
  Mic,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Volume2,
  VolumeX,
  Send,
  Square,
  Bot,
  User,
  LoaderCircle,
} from "lucide-react";
import "./App.css";

const API = "http://localhost:8000";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ProviderInfo = {
  configured: boolean;
  online: boolean;
  model: string;
};

type ProvidersResponse = {
  default_provider: string;
  providers: Record<string, ProviderInfo>;
};

type ChatResponse = {
  session_id: number;
  provider: string;
  model: string;
  response: string;
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | null>(null);

  const [provider, setProvider] = useState("ollama");
  const [model, setModel] = useState("qwen2.5:3b");
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [models, setModels] = useState<string[]>([]);

  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [recording, setRecording] = useState(false);
  const [status, setStatus] = useState("Connecting to Jarvis...");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);


  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }

    setSpeaking(false);
  }, []);

  const loadProviders = useCallback(async () => {
    try {
      const response = await fetch(`${API}/api/providers/`);

      if (!response.ok) {
        throw new Error("Could not retrieve providers.");
      }

      const data: ProvidersResponse = await response.json();

      setProviders(data.providers);

      const defaultProvider = data.default_provider;
      setProvider(defaultProvider);

      if (data.providers[defaultProvider]) {
        setModel(data.providers[defaultProvider].model);
      }

      setConnected(true);
      setStatus("Jarvis online");
    } catch {
      setConnected(false);
      setStatus("Backend offline");
    }
  }, []);

  const loadModels = useCallback(async () => {
    if (provider !== "ollama") {
      setModels([]);
      return;
    }

    try {
      const response = await fetch(`${API}/api/providers/ollama/models`);

      if (!response.ok) {
        throw new Error("Could not retrieve Ollama models.");
      }

      const data: { models: string[] } = await response.json();

      setModels(data.models);

      if (data.models.length > 0 && !data.models.includes(model)) {
        setModel(data.models[0]);
      }
    } catch {
      setModels([]);
    }
  }, [provider, model]);

  useEffect(() => {
    void loadProviders();
  }, [loadProviders]);

  useEffect(() => {
    if (connected) {
      void loadModels();
    }
  }, [connected, loadModels]);

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
      }

      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
      }

      if (mediaRecorderRef.current?.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  const speak = async (text: string) => {
    if (!voiceEnabled || !text.trim()) return;

    stopAudio();
    setSpeaking(true);
    setStatus("Jarvis is speaking...");

    try {
      const response = await fetch(`${API}/api/voice/speak`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text: text.slice(0, 5000) }),
      });

      if (!response.ok) {
        throw new Error("Voice generation failed.");
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      audioUrlRef.current = url;

      const audio = new Audio(url);
      audioRef.current = audio;

      audio.onended = () => {
        stopAudio();
        setStatus("Jarvis online");
      };

      audio.onerror = () => {
        stopAudio();
        setStatus("Audio playback failed");
      };

      await audio.play();
    } catch (error) {
      stopAudio();
      setStatus(
        error instanceof Error ? error.message : "Voice unavailable"
      );
    }
  };

  const sendMessage = async (messageOverride?: string) => {
    const message = (messageOverride ?? input).trim();

    if (!message || loading || !connected) return;

    setInput("");
    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
    ]);

    setLoading(true);
    setStatus("Jarvis is thinking...");

    try {
      const response = await fetch(`${API}/api/chat/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          provider,
          model,
        }),
      });

      const data: ChatResponse | { detail?: string } =
        await response.json();

      if (!response.ok) {
        throw new Error(
          "detail" in data ? data.detail || "Chat request failed." : "Chat request failed."
        );
      }

      const result = data as ChatResponse;

      setSessionId(result.session_id);

      setMessages((previous) => [
        ...previous,
        { role: "assistant", content: result.response },
      ]);

      setStatus(`Online · ${result.provider} · ${result.model}`);

      if (voiceEnabled) {
        void speak(result.response);
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Something went wrong.";

      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content: `I encountered an error: ${errorMessage}`,
        },
      ]);

      setStatus("Request failed");
    } finally {
      setLoading(false);
    }
  };

  const startRecording = async () => {
    if (recording || loading) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });

      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg",
      ].find((type) => MediaRecorder.isTypeSupported(type));

      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      audioChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setRecording(false);
        setStatus("Transcribing audio...");

        stream.getTracks().forEach((track) => track.stop());

        try {
          const audioBlob = new Blob(audioChunksRef.current, {
            type: recorder.mimeType || "audio/webm",
          });

          const extension = audioBlob.type.includes("ogg")
            ? "ogg"
            : audioBlob.type.includes("wav")
              ? "wav"
              : "webm";

          const formData = new FormData();
          formData.append("file", audioBlob, `recording.${extension}`);

          const response = await fetch(`${API}/api/voice/transcribe`, {
            method: "POST",
            body: formData,
          });

          const data: {
            text: string;
            language: string;
            language_probability: number;
          } = await response.json();

          if (!response.ok) {
            throw new Error(
              "text" in data ? data.text : "Transcription failed."
            );
          }

          if (!data.text?.trim()) {
            throw new Error("No speech was detected. Try recording again.");
          }

          setStatus("Transcription complete");
          await sendMessage(data.text);
        } catch (error) {
          setStatus(
            error instanceof Error ? error.message : "Transcription failed"
          );
        }
      };

      recorder.start();
      setRecording(true);
      setStatus("Listening...");
    } catch {
      setStatus("Microphone permission unavailable");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  };

  const newConversation = () => {
    setMessages([]);
    setSessionId(null);
    setInput("");
    stopAudio();
    setStatus("New conversation ready");
  };

  const handleProviderChange = (nextProvider: string) => {
    setProvider(nextProvider);

    if (providers[nextProvider]) {
      setModel(providers[nextProvider].model);
    }
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">
            <Command size={23} />
          </div>
          <div>
            <h1>JARVIS</h1>
            <span>PERSONAL AI SYSTEM</span>
          </div>
        </div>

        <button className="new-chat" onClick={newConversation}>
          <Plus size={17} />
          New conversation
        </button>

        <div className="sidebar-section">
          <span className="section-label">WORKSPACE</span>
          <div className="sidebar-item active">
            <MessageSquare size={17} />
            <span>Chat</span>
          </div>
          <div className="sidebar-item">
            <Activity size={17} />
            <span>Activity</span>
          </div>
          <div className="sidebar-item">
            <Cpu size={17} />
            <span>AI Providers</span>
          </div>
        </div>

        <div className="sidebar-section conversations">
          <span className="section-label">CURRENT SESSION</span>
          <p className="empty-history">
            {sessionId ? `Session #${sessionId}` : "No active session"}
          </p>
        </div>

        <div className="sidebar-bottom">
          <div className="sidebar-item">
            <Settings size={17} />
            <span>Settings</span>
          </div>
          <div className="sidebar-item">
            <CircleHelp size={17} />
            <span>Help</span>
          </div>
          <div className="profile">
            <div className="profile-avatar">J</div>
            <div>
              <strong>Jarvis</strong>
              <span>Local assistant</span>
            </div>
            <ChevronDown size={16} />
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu">
              <Menu size={20} />
            </button>
            <div>
              <div className="breadcrumb">WORKSPACE / CHAT</div>
              <h2>Conversation</h2>
            </div>
          </div>

          <div className="topbar-right">
            <div className="connection-status">
              <span
                className="status-dot"
                style={{
                  background: connected ? "#54d69a" : "#e5a94f",
                }}
              />
              {status}
            </div>
            <button
              className="icon-button"
              title="Refresh backend connection"
              onClick={() => void loadProviders()}
            >
              <Search size={18} />
            </button>
          </div>
        </header>

        <div className="provider-toolbar">
          <label>
            AI PROVIDER
            <select
              value={provider}
              onChange={(event) => handleProviderChange(event.target.value)}
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
                onChange={(event) => setModel(event.target.value)}
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
            onClick={() => {
              setVoiceEnabled((value) => !value);
              if (voiceEnabled) stopAudio();
            }}
            title="Toggle voice responses"
          >
            {voiceEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
            Voice {voiceEnabled ? "on" : "off"}
          </button>
        </div>

        <section className="chat-area conversation-area">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="orb-container">
                <div className="orb-ring ring-one" />
                <div className="orb-ring ring-two" />
                <div className="orb-ring ring-three" />
                <div className="orb">
                  <AudioLines size={43} strokeWidth={1.3} />
                </div>
              </div>

              <div className="welcome-eyebrow">
                <Sparkles size={14} />
                PERSONAL AI ASSISTANT
              </div>

              <h1>
                At your service<span>.</span>
              </h1>

              <p className="welcome-description">
                Your personal intelligence system is online.
                <br />
                Start a conversation with Jarvis.
              </p>

              <div className="capability-grid">
                <div className="capability">
                  <div className="capability-icon">
                    <MessageSquare size={19} />
                  </div>
                  <div>
                    <strong>Intelligent chat</strong>
                    <span>AI-powered conversations</span>
                  </div>
                </div>

                <div className="capability">
                  <div className="capability-icon">
                    <Volume2 size={19} />
                  </div>
                  <div>
                    <strong>Voice responses</strong>
                    <span>Powered by Piper TTS</span>
                  </div>
                </div>

                <div className="capability">
                  <div className="capability-icon">
                    <ShieldCheck size={19} />
                  </div>
                  <div>
                    <strong>Secure actions</strong>
                    <span>Permission-based execution</span>
                  </div>
                </div>

                <div className="capability">
                  <div className="capability-icon">
                    <Cpu size={19} />
                  </div>
                  <div>
                    <strong>Local intelligence</strong>
                    <span>Your own AI infrastructure</span>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="message-list">
              {messages.map((message, index) => (
                <div
                  className={`message-row ${message.role}`}
                  key={`${index}-${message.role}`}
                >
                  <div className="message-avatar">
                    {message.role === "assistant" ? (
                      <Bot size={19} />
                    ) : (
                      <User size={19} />
                    )}
                  </div>
                  <div className="message-content">
                    <span className="message-author">
                      {message.role === "assistant" ? "JARVIS" : "YOU"}
                    </span>
                    <p>{message.content}</p>
                    {message.role === "assistant" && (
                      <button
                        className="message-speak"
                        onClick={() => void speak(message.content)}
                        title="Read this response aloud"
                      >
                        <Volume2 size={15} />
                        Read aloud
                      </button>
                    )}
                  </div>
                </div>
              ))}

              {loading && (
                <div className="message-row assistant">
                  <div className="message-avatar">
                    <Bot size={19} />
                  </div>
                  <div className="message-content">
                    <span className="message-author">JARVIS</span>
                    <p className="thinking-indicator">
                      <LoaderCircle size={16} className="spin" />
                      Thinking...
                    </p>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </section>

        <footer className="composer-area">
          <div className="composer">
            <input
              id="jarvis-chat-input"
              name="message"
              type="text"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
              placeholder="Message Jarvis..."
              disabled={loading || recording}
            />

            <div className="composer-actions">
              {speaking && (
                <button
                  className="icon-button"
                  onClick={stopAudio}
                  title="Stop speaking"
                >
                  <Square size={16} />
                </button>
              )}

              <button
                className={`icon-button ${recording ? "recording" : ""}`}
                onClick={recording ? stopRecording : startRecording}
                disabled={!connected || loading}
                title={recording ? "Stop recording" : "Start voice input"}
              >
                {recording ? <Square size={17} /> : <Mic size={19} />}
              </button>

              <button
                className="send-button"
                onClick={() => void sendMessage()}
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
      </main>
    </div>
  );
}

export default App;
