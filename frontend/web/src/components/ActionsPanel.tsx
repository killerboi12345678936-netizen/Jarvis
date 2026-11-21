import { useCallback, useEffect, useState } from "react";
import { Check, RefreshCw, ShieldCheck, X } from "lucide-react";
import { SlideOver } from "./SlideOver";
import { apiGet, apiPost } from "../lib/api";

export type ToolAction = {
  id: number;
  tool_name: string;
  arguments: string;
  status: string;
  result: string | null;
  created_at: string;
  updated_at: string;
};

type ActionsPanelProps = {
  onClose: () => void;
  onChanged: () => void;
};

const STATUS_FILTERS = [
  "pending",
  "approved",
  "rejected",
  "failed",
] as const;

export function ActionsPanel({ onClose, onChanged }: ActionsPanelProps) {
  const [actions, setActions] = useState<ToolAction[]>([]);
  const [filter, setFilter] = useState<(typeof STATUS_FILTERS)[number] | "all">("pending");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadActions = useCallback(async () => {
    try {
      const path =
        filter === "all"
          ? "/api/actions/"
          : `/api/actions/?status=${filter}`;

      const data = await apiGet<{ actions: ToolAction[] }>(path);

      setActions(data.actions);
      setError(null);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Could not load actions.",
      );
    }
  }, [filter]);

  useEffect(() => {
    void loadActions();

    if (filter !== "pending") {
      return;
    }

    const interval = setInterval(() => void loadActions(), 5000);

    return () => clearInterval(interval);
  }, [loadActions, filter]);

  const decide = async (action: ToolAction, approve: boolean) => {
    setBusyId(action.id);

    try {
      await apiPost(
        `/api/actions/${action.id}/${approve ? "approve" : "reject"}`,
      );

      await loadActions();
      onChanged();
    } catch (decideError) {
      setError(
        decideError instanceof Error
          ? decideError.message
          : "Action failed.",
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <SlideOver
      title="Agent actions"
      subtitle="Approve or reject Jarvis's proposed actions"
      onClose={onClose}
    >
      <div className="panel-toolbar">
        <div className="chip-row">
          {(["pending", "approved", "rejected", "failed", "all"] as const).map(
            (option) => (
              <button
                key={option}
                className={`chip ${filter === option ? "active" : ""}`}
                onClick={() => setFilter(option)}
              >
                {option}
              </button>
            ),
          )}
        </div>

        <button
          className="icon-button"
          onClick={() => void loadActions()}
          title="Refresh"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {error && <div className="voice-error">{error}</div>}

      <div className="action-list">
        {actions.length === 0 ? (
          <p className="panel-empty">
            No {filter === "all" ? "" : filter} actions.
          </p>
        ) : (
          actions.map((action) => {
            let argumentsPreview = "";

            try {
              argumentsPreview = JSON.stringify(
                JSON.parse(action.arguments),
                null,
                2,
              );
            } catch {
              argumentsPreview = action.arguments;
            }

            return (
              <div className="action-card" key={action.id}>
                <div className="action-head">
                  <span className="action-tool">
                    <ShieldCheck size={14} />
                    {action.tool_name}
                  </span>
                  <span className={`action-status ${action.status}`}>
                    {action.status}
                  </span>
                </div>

                <pre className="action-arguments">
                  {argumentsPreview}
                </pre>

                {action.result && (
                  <pre className="action-result">{action.result}</pre>
                )}

                {action.status === "pending" && (
                  <div className="action-buttons">
                    <button
                      className="action-approve"
                      disabled={busyId === action.id}
                      onClick={() => void decide(action, true)}
                    >
                      <Check size={15} />
                      Approve &amp; run
                    </button>
                    <button
                      className="action-reject"
                      disabled={busyId === action.id}
                      onClick={() => void decide(action, false)}
                    >
                      <X size={15} />
                      Reject
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </SlideOver>
  );
}
