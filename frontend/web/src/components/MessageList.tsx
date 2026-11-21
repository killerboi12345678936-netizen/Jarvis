import { useEffect, useRef } from "react";
import {
  AudioLines,
  Bot,
  Cpu,
  LoaderCircle,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  User,
  Volume2,
} from "lucide-react";

export type Message = {
  role: "user" | "assistant";
  content: string;
};

type MessageListProps = {
  messages: Message[];
  loading: boolean;
  onSpeak: (text: string) => void;
};

export function MessageList({
  messages,
  loading,
  onSpeak,
}: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  if (messages.length === 0) {
    return (
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
    );
  }

  return (
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
            {message.role === "assistant" && message.content && (
              <button
                className="message-speak"
                onClick={() => onSpeak(message.content)}
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
  );
}
