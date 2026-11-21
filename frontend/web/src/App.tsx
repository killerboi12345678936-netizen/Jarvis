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

type StreamEvent = {
  type: "start" | "chunk" | "done" | "error";
  session_id?: number;
  provider?: string;
  model?: string;
  text?: string;
  response?: string;
  message?: string;
};

// Words after which a period does not end a sentence, plus single-letter
// initials such as "J." or the "e." in "e.g.".
const SENTENCE_ABBREVIATIONS = new Set([
  "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
  "eg", "ie", "fig", "approx", "dept", "est", "inc", "ltd", "co",
  "corp", "rev", "hon", "capt", "sgt", "gen", "col", "lt", "mt",
  "ft", "apt", "no", "al", "cf", "viz", "ph", "md", "min", "max",
  "sec", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
  "sept", "oct", "nov", "dec",
]);

// Quotes, brackets, and markdown emphasis that may trail sentence punctuation.
const SENTENCE_CLOSERS = new Set([
  "\"", "'", ")", "]", "}", "`", "*",
]);

const fetchTtsAudio = async (
  endpoint: string,
  text: string,
  signal: AbortSignal,
): Promise<Blob> => {
  const response = await fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!response.ok) {
    throw new Error("Voice generation failed.");
  }

  return response.blob();
};

const endsWithAbbreviation = (text: string) => {
  const match = /([A-Za-z]+)\s*$/.exec(text);

  if (!match) return false;

  const word = match[1].toLowerCase();

  return SENTENCE_ABBREVIATIONS.has(word) || word.length === 1;
};

const endsWithListItemNumber = (text: string) => {
  const lineStart = text.lastIndexOf("\n") + 1;

  return /^\d+$/.test(text.slice(lineStart));
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
  const speechRunRef = useRef(0);
  const speechAbortRef = useRef<AbortController | null>(null);


  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const stopAudio = useCallback(() => {
    speechRunRef.current += 1;
    speechAbortRef.current?.abort();
    speechAbortRef.current = null;

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
      speechAbortRef.current?.abort();

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

  const playAudioBlob = async (
    blob: Blob,
    speechRun: number,
  ): Promise<boolean> => {
    if (speechRunRef.current !== speechRun) return false;

    const url = URL.createObjectURL(blob);
    audioUrlRef.current = url;

    const audio = new Audio(url);
    audioRef.current = audio;

    setSpeaking(true);
    setStatus("Jarvis is speaking...");

    const completed = await new Promise<boolean>((resolve) => {
      let settled = false;

      const finish = (playedToEnd: boolean) => {
        if (settled) return;
        settled = true;

        audio.onended = null;
        audio.onerror = null;
        audio.onpause = null;

        if (audioRef.current === audio) {
          audioRef.current = null;
        }

        URL.revokeObjectURL(url);

        if (audioUrlRef.current === url) {
          audioUrlRef.current = null;
        }

        resolve(playedToEnd);
      };

      audio.onended = () => finish(true);
      audio.onerror = () => finish(false);
      audio.onpause = () => finish(false);

      void audio.play().catch(() => finish(false));
    });

    if (speechRunRef.current === speechRun) {
      setSpeaking(false);
    }

    return completed;
  };

  const speak = async (text: string) => {
    if (!voiceEnabled || !text.trim()) return;

    stopAudio();

    const speechRun = speechRunRef.current;
    const controller = new AbortController();
    speechAbortRef.current = controller;

    setSpeaking(true);
    setStatus("Jarvis is speaking...");

    try {
      const blob = await fetchTtsAudio(
        "/api/voice/speak",
        text.slice(0, 5000),
        controller.signal,
      );

      const completed = await playAudioBlob(blob, speechRun);

      if (speechRunRef.current === speechRun) {
        setStatus(completed ? "Jarvis online" : "Audio playback failed");
      }
    } catch (error) {
      if (speechRunRef.current === speechRun) {
        setSpeaking(false);
        setStatus(
          error instanceof Error ? error.message : "Voice unavailable",
        );
      }
    }
  };


  const sendMessage = async (messageOverride?: string) => {
    const message = (messageOverride ?? input).trim();

    if (!message || loading || !connected) return;

    setInput("");

    setMessages((previous) => [
      ...previous,
      { role: "user", content: message },
      { role: "assistant", content: "" },
    ]);

    setLoading(true);
    setStatus("Jarvis is thinking...");

    // Stop any previous speech and create a new speech run for this response.
    stopAudio();

    const speechRun = speechRunRef.current;
    const speechController = new AbortController();
    speechAbortRef.current = speechController;
    const shouldSpeak = voiceEnabled;

    let fullResponse = "";
    let speechBuffer = "";
    let playbackChain: Promise<void> = Promise.resolve();

    const enqueueSentence = (sentence: string) => {
      const cleanSentence = sentence.trim();

      if (
        !cleanSentence ||
        !shouldSpeak ||
        speechRunRef.current !== speechRun
      ) {
        return;
      }

      // Generate audio as soon as a complete sentence is available.
      const audioPromise = fetchTtsAudio(
        "/api/voice/speak/sentence",
        cleanSentence,
        speechController.signal,
      );

      // Keep playback in sentence order while audio generation overlaps.
      playbackChain = playbackChain.then(async () => {
        try {
          const blob = await audioPromise;

          if (speechRunRef.current !== speechRun) return;

          await playAudioBlob(blob, speechRun);
        } catch (error) {
          if (speechRunRef.current === speechRun) {
            console.error("Sentence audio error:", error);
          }
        }
      });
    };

    const extractCompleteSentences = () => {
      const boundaries: number[] = [];

      for (let i = 0; i < speechBuffer.length; i += 1) {
        if (!".!?".includes(speechBuffer[i])) {
          continue;
        }

        let end = i;

        while (
          end + 1 < speechBuffer.length &&
          ".!?".includes(speechBuffer[end + 1])
        ) {
          end += 1;
        }

        while (
          end + 1 < speechBuffer.length &&
          SENTENCE_CLOSERS.has(speechBuffer[end + 1])
        ) {
          end += 1;
        }

        const atEnd = end + 1 >= speechBuffer.length;
        const nextChar = atEnd ? "" : speechBuffer[end + 1];
        const before = speechBuffer.slice(0, i);

        // Periods that belong to abbreviations ("Dr.", "e.g."), numbered
        // markdown lists ("1. Item"), decimals ("3.14"), or a number whose
        // continuation has not arrived yet do not end a sentence.
        if (speechBuffer[i] === ".") {
          const isListNumber =
            /\s/.test(nextChar) && endsWithListItemNumber(before);

          const isDecimalOrTruncatedNumber =
            /\d$/.test(before) && (/\d/.test(nextChar) || atEnd);

          if (
            endsWithAbbreviation(before) ||
            isListNumber ||
            isDecimalOrTruncatedNumber
          ) {
            i = end;
            continue;
          }
        }

        // A punctuation run only completes a sentence when followed by
        // whitespace or the end of the currently buffered text.
        if (!atEnd && !/\s/.test(nextChar)) {
          i = end;
          continue;
        }

        boundaries.push(end);
        i = end;
      }

      if (boundaries.length === 0) {
        return;
      }

      let consumed = 0;

      for (const boundary of boundaries) {
        enqueueSentence(speechBuffer.slice(consumed, boundary + 1));
        consumed = boundary + 1;
      }

      speechBuffer = speechBuffer.slice(consumed);
    };

    try {
      const response = await fetch(`${API}/api/chat/stream`, {
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

      if (!response.ok) {
        let errorMessage = "Chat request failed.";

        try {
          const data = await response.json();
          errorMessage = data.detail || errorMessage;
        } catch {
          // Keep the default error message.
        }

        throw new Error(errorMessage);
      }

      if (!response.body) {
        throw new Error("Streaming response unavailable.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";
      let completed = false;

      const processEvent = (block: string) => {
        const dataLines = block
          .split(/\r?\n/)
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim());

        if (dataLines.length === 0) return;

        let event: StreamEvent;

        try {
          event = JSON.parse(dataLines.join("\n")) as StreamEvent;
        } catch {
          console.warn("Ignoring malformed stream event.");
          return;
        }

        if (
          event.type === "start" &&
          typeof event.session_id === "number"
        ) {
          setSessionId(event.session_id);
          setStatus("Jarvis is responding...");
        }

        if (event.type === "chunk" && typeof event.text === "string") {
          fullResponse += event.text;

          setMessages((previous) => {
            const updated = [...previous];
            const lastIndex = updated.length - 1;

            if (updated[lastIndex]?.role === "assistant") {
              updated[lastIndex] = {
                ...updated[lastIndex],
                content: fullResponse,
              };
            }

            return updated;
          });

          if (shouldSpeak) {
            speechBuffer += event.text;
            extractCompleteSentences();
          }
        }

        if (event.type === "done") {
          completed = true;

          if (typeof event.response === "string") {
            fullResponse = event.response;

            setMessages((previous) => {
              const updated = [...previous];
              const lastIndex = updated.length - 1;

              if (updated[lastIndex]?.role === "assistant") {
                updated[lastIndex] = {
                  ...updated[lastIndex],
                  content: fullResponse,
                };
              }

              return updated;
            });
          }

          setStatus(`Online · ${event.provider} · ${event.model}`);
        }

        if (event.type === "error") {
          throw new Error(event.message || "Streaming failed.");
        }
      };

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? "";

        for (const block of blocks) {
          processEvent(block);
        }
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        processEvent(buffer);
      }

      if (!completed) {
        throw new Error("The streaming connection ended unexpectedly.");
      }

      // Flush the final text, even if it doesn't end with punctuation.
      if (speechBuffer.trim()) {
        enqueueSentence(speechBuffer);
        speechBuffer = "";
      }

      // Update the status when the final queued sentence finishes playing.
      if (shouldSpeak) {
        void playbackChain.then(() => {
          if (speechRunRef.current === speechRun) {
            setSpeaking(false);
            setStatus("Jarvis online");
          }
        });
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : "Something went wrong.";

      setMessages((previous) => {
        const updated = [...previous];
        const lastIndex = updated.length - 1;

        if (updated[lastIndex]?.role === "assistant") {
          const existing = updated[lastIndex].content;

          updated[lastIndex] = {
            ...updated[lastIndex],
            content: existing
              ? `${existing}\n\nI encountered an error: ${errorMessage}`
              : `I encountered an error: ${errorMessage}`,
          };
        }

        return updated;
      });

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

          const data: { text?: string; detail?: string } | null =
            await response.json().catch(() => null);

          if (!response.ok) {
            throw new Error(data?.detail || "Transcription failed.");
          }

          if (!data?.text?.trim()) {
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
            <span>JARVIS AI Â· V1.0</span>
            <span>
              {recording
                ? "Recording Â· press stop when finished"
                : "Text and voice interface"}
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
}

export default App;
