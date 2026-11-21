import {
  Brain,
  CalendarClock,
  ChevronDown,
  Command,
  CircleHelp,
  MessageSquare,
  Plus,
  Settings,
  ShieldCheck,
} from "lucide-react";

export type PanelId =
  | "memory"
  | "integrations"
  | "actions"
  | "settings";

export type SessionSummary = {
  id: number;
  created_at: string;
  closed_at: string | null;
  last_message: string | null;
};

type SidebarProps = {
  connected: boolean;
  sessionId: number | null;
  sessions: SessionSummary[];
  activeSessionId: number | null;
  pendingActions: number;
  onNewConversation: () => void;
  onOpenPanel: (panel: PanelId) => void;
  onSelectSession: (id: number) => void;
};

export function Sidebar({
  connected,
  sessionId,
  sessions,
  activeSessionId,
  pendingActions,
  onNewConversation,
  onOpenPanel,
  onSelectSession,
}: SidebarProps) {
  return (
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

      <button className="new-chat" onClick={onNewConversation}>
        <Plus size={17} />
        New conversation
      </button>

      <div className="sidebar-section">
        <span className="section-label">WORKSPACE</span>
        <div className="sidebar-item active">
          <MessageSquare size={17} />
          <span>Chat</span>
        </div>
        <button
          className="sidebar-item as-button"
          onClick={() => onOpenPanel("memory")}
        >
          <Brain size={17} />
          <span>Memory</span>
        </button>
        <button
          className="sidebar-item as-button"
          onClick={() => onOpenPanel("integrations")}
        >
          <CalendarClock size={17} />
          <span>Integrations</span>
        </button>
        <button
          className="sidebar-item as-button"
          onClick={() => onOpenPanel("actions")}
        >
          <ShieldCheck size={17} />
          <span>Actions</span>
          {pendingActions > 0 && (
            <span className="sidebar-badge">{pendingActions}</span>
          )}
        </button>
        <button
          className="sidebar-item as-button"
          onClick={() => onOpenPanel("settings")}
        >
          <Settings size={17} />
          <span>Settings</span>
        </button>
      </div>

      <div className="sidebar-section conversations">
        <span className="section-label">CONVERSATIONS</span>
        <div className="session-list">
          {sessions.length === 0 ? (
            <p className="empty-history">
              {connected
                ? "No conversations yet."
                : "Waiting for backend..."}
            </p>
          ) : (
            sessions.map((session) => (
              <button
                key={session.id}
                className={`session-item ${
                  session.id === activeSessionId ? "active" : ""
                }`}
                onClick={() => onSelectSession(session.id)}
                title={session.last_message ?? undefined}
              >
                <span className="session-name">
                  Session #{session.id}
                </span>
                <span className="session-preview">
                  {session.last_message
                    ? session.last_message.slice(0, 38)
                    : "Empty session"}
                </span>
              </button>
            ))
          )}
        </div>
      </div>

      <div className="sidebar-bottom">
        <div className="sidebar-item">
          <CircleHelp size={17} />
          <span>Help</span>
        </div>
        <div className="profile">
          <div className="profile-avatar">J</div>
          <div>
            <strong>Jarvis</strong>
            <span>
              {sessionId
                ? `Session #${sessionId}`
                : "Local assistant"}
            </span>
          </div>
          <ChevronDown size={16} />
        </div>
      </div>
    </aside>
  );
}
