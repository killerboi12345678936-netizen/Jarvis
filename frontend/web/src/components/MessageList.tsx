import { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  Bot,
  Check,
  Cpu,
  FileText,
  LoaderCircle,
  MessageSquare,
  ShieldCheck,
  Sparkles,
  User,
  Volume2,
  X,
} from "lucide-react";
import { apiPost } from "../lib/api";

export type ProposedAction = {
  action_id: number;
  tool: string;
  arguments: Record<string, unknown>;
  description: string;
  status: "pending" | "approved" | "rejected" | "failed";
  result?: string | null;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  actions?: ProposedAction[];
};

type MessageListProps = {
  messages: Message[];
  loading: boolean;
  onSpeak: (text: string) => void;
  onActionUpdate: (
    messageIndex: number,
    actionId: number,
    patch: Partial<ProposedAction>,
  ) => void;
  onActionsChanged: () => void;
};

const describeAction = (action: ProposedAction): string => {
  const args = action.arguments;

  if (action.tool === "create_note") {
    return `Create file "${String(args.filename ?? "?")}" with content: ${String(args.content ?? "")}`;
  }

  if (action.tool === "open_application") {
    return `Open application "${String(args.name ?? "?")}"`;
  }

  if (action.tool === "create_event") {
    return `Calendar event "${String(args.title ?? "?")}" from ${String(args.start ?? "?")} to ${String(args.end ?? "?")}`;
  }

  if (action.tool === "delete_event") {
    return `Delete event #${String(args.event_id ?? "?")}`;
  }

  return action.description;
};

const summarizeResult = (action: ProposedAction): string | null => {
  if (!action.result) return null;

  try {
    const data = JSON.parse(action.result);

    if (action.tool === "create_note" && data.location) {
      return `File created and verified: ${data.location}`;
    }

    return JSON.stringify(data, null, 2);
  } catch {
    return action.result;
  }
};

function ActionCard({
  action,
  onDecided,
}: {
  action: ProposedAction;
  onDecided: (status: ProposedAction["status"], result: string | null) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decide = async (approve: boolean) => {
    if (busy) return;

    setBusy(true);
    setError(null);

    try {
      const data = await apiPost<{
        success: boolean;
        status: string;
        result?: unknown;
      }>(`/api/actions/${action.action_id}/${approve ? "approve" : "reject"}`);

      onDecided(
        approve ? "approved" : "rejected",
        approve && data.result !== undefined
          ? JSON.stringify(data.result)
          : null,
      );
    } catch (decideError) {
      const message =
        decideError instanceof Error
          ? decideError.message
          : "Action failed.";

      setError(message);
      onDecided("failed", message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`action-card-inline ${action.status}`}>
      <div className="action-card-head">
        <FileText size={15} />
        <span className="action-card-tool">{action.tool}</span>
        <span className={`action-status ${action.status}`}>
          {action.status}
        </span>
      </div>

      <p className="action-card-summary">{describeAction(action)}</p>

      {action.status === "approved" && (
        <p className="action-card-result ok">
          {summarizeResult(action) ?? "Done."}
        </p>
      )}

      {action.status === "failed" && (
        <p className="action-card-result error">
          {summarizeResult(action) ?? "The action failed."}
        </p>
      )}

      {action.status === "rejected" && (
        <p className="action-card-result">Rejected - nothing was changed.</p>
      )}

      {error && action.status === "pending" && (
        <p className="action-card-result error">{error}</p>
      )}

      {action.status === "pending" && (
        <div className="action-buttons">
          <button
            className="action-approve"
            disabled={busy}
            onClick={() => void decide(true)}
          >
            <Check size={15} />
            {busy ? "Running..." : "Approve & run"}
          </button>
          <button
            className="action-reject"
            disabled={busy}
            onClick={() => void decide(false)}
          >
            <X size={15} />
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

export function MessageList({
  messages,
  loading,
  onSpeak,
  onActionUpdate,
  onActionsChanged,
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
              <span>Approve each action in chat</span>
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
            {message.content && <p>{message.content}</p>}
            {message.actions?.map((action) => (
              <ActionCard
                key={action.action_id}
                action={action}
                onDecided={(status, result) => {
                  onActionUpdate(index, action.action_id, {
                    status,
                    result,
                  });
                  onActionsChanged();
                }}
              />
            ))}
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
