import { useCallback, useEffect, useRef, useState } from "react";
import { Menu, Search } from "lucide-react";
import "./App.css";

import { apiGet, API, fetchTtsAudio } from "./lib/api";
import {
  extractCompleteSentences,
} from "./lib/segmentation";
import type { VoiceTuning } from "./lib/voiceClient";

import { Composer } from "./components/Composer";
import { LiveVoicePanel } from "./components/LiveVoicePanel";
import { MessageList, type Message } from "./components/MessageList";
import { ProviderToolbar } from "./components/ProviderToolbar";
import { Sidebar, type PanelId, type SessionSummary } from "./components/Sidebar";
import { MemoryPanel } from "./components/MemoryPanel";
import { ActionsPanel } from "./components/ActionsPanel";
import { IntegrationsPanel } from "./components/IntegrationsPanel";
import { SettingsPanel } from "./components/SettingsPanel";

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

type StoredMessage = {
  role: string;
  content: string;
};

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);

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
  const [activePanel, setActivePanel] = useState<PanelId | null>(null);
  const [liveVoiceOpen, setLiveVoiceOpen] = useState(false);
  const [pendingActions, setPendingActions] = useState(0);
  const [tuning, setTuning] = useState<VoiceTuning>({
    continuous: true,
    speechThreshold: 0.015,
    silenceMs: 900,
    minSpeechMs: 300,
    bargeInThreshold: 0.035,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const speechRunRef = useRef(0);
  const speechAbortRef = useRef<AbortController | null>(null);

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

  const playAudioBlob = useCallback(
    async (blob: Blob, speechRun: number): Promise<boolean> => {
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
    },
    [],
  );

  const speak = useCallback(
    async (text: string) => {
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
    },
    [voiceEnabled, stopAudio, playAudioBlob],
  );

  const loadProviders = useCallback(async () => {
    try {
      const data = await apiGet<ProvidersResponse>("/api/providers/");

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
      const data = await apiGet<{ models: string[] }>(
        "/api/providers/ollama/models",
      );

      setModels(data.models);

      if (data.models.length > 0 && !data.models.includes(model)) {
        setModel(data.models[0]);
      }
    } catch {
      setModels([]);
    }
  }, [provider, model]);

  const loadSessions = useCallback(async () => {
    try {
      const data = await apiGet<{ sessions: SessionSummary[] }>(
        "/api/sessions/",
      );

      setSessions(data.sessions);
    } catch {
      // Sidebar history is best-effort.
    }
  }, []);

  const loadPendingActions = useCallback(async () => {
    try {
      const data = await apiGet<{ actions: { id: number }[] }>(
        "/api/actions/?status=pending",
      );

      setPendingActions(data.actions.length);
    } catch {
      setPendingActions(0);
    }
  }, []);

  useEffect(() => {
    void loadProviders();
  }, [loadProviders]);

  useEffect(() => {
    if (connected) {
      void loadModels();
      void loadSessions();
      void loadPendingActions();
    }
  }, [connected, loadModels, loadSessions, loadPendingActions]);

  useEffect(() => {
    const interval = setInterval(() => void loadPendingActions(), 10000);

    return () => clearInterval(interval);
  }, [loadPendingActions]);

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

  const selectSession = async (id: number) => {
    try {
      const data = await apiGet<{
        session: SessionSummary;
        messages: StoredMessage[];
      }>(`/api/sessions/${id}`);

      stopAudio();

      setMessages(
        data.messages
          .filter(
            (message) =>
              message.role === "user" || message.role === "assistant",
          )
          .map((message) => ({
            role: message.role as Message["role"],
            content: message.content,
          })),
      );

      setSessionId(id);
      setActiveSessionId(id);
      setStatus(`Viewing session #${id}`);
    } catch (error) {
      setStatus(
        error instanceof Error ? error.message : "Could not load session.",
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
      { role: "assistant", content: "" },
    ]);

    setLoading(true);
    setStatus("Jarvis is thinking...");

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

      const audioPromise = fetchTtsAudio(
        "/api/voice/speak/sentence",
        cleanSentence,
        speechController.signal,
      );

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
        },
      );

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
          setActiveSessionId(event.session_id);
          setStatus("Jarvis is responding...");
          void loadSessions();
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

            const { sentences, remaining } =
              extractCompleteSentences(speechBuffer);

            speechBuffer = remaining;

            for (const sentence of sentences) {
              enqueueSentence(sentence);
            }
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

      if (speechBuffer.trim()) {
        enqueueSentence(speechBuffer);
        speechBuffer = "";
      }

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
            error instanceof Error ? error.message : "Transcription failed",
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
    setActiveSessionId(null);
    setInput("");
    stopAudio();
    setStatus("New conversation ready");
  };

  // Live voice mode mirrors the spoken conversation into the chat area.
  const handleVoiceTranscript = (text: string) => {
    if (!text.trim()) return;

    setMessages((previous) => [
      ...previous,
      { role: "user", content: text },
      { role: "assistant", content: "" },
    ]);
  };

  const handleVoiceSentence = (text: string) => {
    setMessages((previous) => {
      const updated = [...previous];
      const lastIndex = updated.length - 1;

      if (updated[lastIndex]?.role === "assistant") {
        updated[lastIndex] = {
          ...updated[lastIndex],
          content: updated[lastIndex].content + text,
        };
      }

      return updated;
    });
  };

  const handleVoiceResponseDone = (
    response: string,
    interrupted: boolean,
  ) => {
    setMessages((previous) => {
      const updated = [...previous];
      const lastIndex = updated.length - 1;

      if (updated[lastIndex]?.role === "assistant") {
        const content = response || updated[lastIndex].content;

        updated[lastIndex] = {
          ...updated[lastIndex],
          content: interrupted
            ? `${content} (interrupted)`
            : content,
        };
      }

      return updated;
    });

    void loadSessions();
  };

  const handleProviderChange = (nextProvider: string) => {
    setProvider(nextProvider);

    if (providers[nextProvider]) {
      setModel(providers[nextProvider].model);
    }
  };

  return (
    <div className="app-shell">
      <Sidebar
        connected={connected}
        sessionId={sessionId}
        sessions={sessions}
        activeSessionId={activeSessionId}
        pendingActions={pendingActions}
        onNewConversation={newConversation}
        onOpenPanel={(panel) => setActivePanel(panel)}
        onSelectSession={(id) => void selectSession(id)}
      />

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

        <ProviderToolbar
          provider={provider}
          model={model}
          providers={providers}
          models={models}
          voiceEnabled={voiceEnabled}
          onProviderChange={handleProviderChange}
          onModelChange={setModel}
          onToggleVoice={() => {
            setVoiceEnabled((value) => !value);
            if (voiceEnabled) stopAudio();
          }}
          onOpenLiveVoice={() => setLiveVoiceOpen(true)}
        />

        <section className="chat-area conversation-area">
          <MessageList
            messages={messages}
            loading={loading}
            onSpeak={(text) => void speak(text)}
          />
        </section>

        <Composer
          input={input}
          loading={loading}
          recording={recording}
          speaking={speaking}
          connected={connected}
          onInputChange={setInput}
          onSend={() => void sendMessage()}
          onStopSpeaking={stopAudio}
          onToggleRecording={() =>
            void (recording ? stopRecording() : startRecording())
          }
        />
      </main>

      {liveVoiceOpen && (
        <LiveVoicePanel
          onClose={() => setLiveVoiceOpen(false)}
          tuning={tuning}
          onTuningChange={(patch) => setTuning((previous) => ({
            ...previous,
            ...patch,
          }))}
          onTranscript={handleVoiceTranscript}
          onSentence={handleVoiceSentence}
          onResponseDone={handleVoiceResponseDone}
        />
      )}

      {activePanel === "memory" && (
        <MemoryPanel onClose={() => setActivePanel(null)} />
      )}

      {activePanel === "actions" && (
        <ActionsPanel
          onClose={() => setActivePanel(null)}
          onChanged={() => void loadPendingActions()}
        />
      )}

      {activePanel === "integrations" && (
        <IntegrationsPanel onClose={() => setActivePanel(null)} />
      )}

      {activePanel === "settings" && (
        <SettingsPanel
          onClose={() => setActivePanel(null)}
          tuning={tuning}
          onTuningChange={(patch) => setTuning((previous) => ({
            ...previous,
            ...patch,
          }))}
        />
      )}
    </div>
  );
}

export default App;
