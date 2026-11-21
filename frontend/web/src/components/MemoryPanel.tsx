import { useCallback, useEffect, useState } from "react";
import { Brain, Plus, RefreshCw, Trash2 } from "lucide-react";
import { SlideOver } from "./SlideOver";
import { apiDelete, apiGet, apiPost, apiPut } from "../lib/api";

export type Memory = {
  id: number;
  content: string;
  category: string;
  created_at: string;
  updated_at: string | null;
};

const CATEGORIES = [
  "general",
  "project",
  "skill",
  "preference",
  "interest",
] as const;

type MemoryPanelProps = {
  onClose: () => void;
};

export function MemoryPanel({ onClose }: MemoryPanelProps) {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [newContent, setNewContent] = useState("");
  const [newCategory, setNewCategory] =
    useState<(typeof CATEGORIES)[number]>("general");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadMemories = useCallback(async () => {
    const params = new URLSearchParams();

    if (category !== "all") {
      params.set("category", category);
    }

    if (search.trim()) {
      params.set("search", search.trim());
    }

    try {
      const data = await apiGet<{ memories: Memory[] }>(
        `/api/memories/?${params.toString()}`,
      );

      setMemories(data.memories);
      setError(null);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Could not load memories.",
      );
    }
  }, [category, search]);

  useEffect(() => {
    void loadMemories();
  }, [loadMemories]);

  const createMemory = async () => {
    if (!newContent.trim()) {
      return;
    }

    setBusy(true);

    try {
      const result = await apiPost<{ duplicate: boolean }>(
        "/api/memories/",
        {
          content: newContent.trim(),
          category: newCategory,
        },
      );

      setNotice(
        result.duplicate
          ? "Very similar to an existing memory — kept as one entry."
          : "Memory saved. Jarvis will use it in future conversations.",
      );

      setNewContent("");
      await loadMemories();
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : "Could not save memory.",
      );
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (memory: Memory) => {
    if (!editDraft.trim() || editDraft === memory.content) {
      setEditingId(null);
      return;
    }

    try {
      await apiPut(`/api/memories/${memory.id}`, {
        content: editDraft.trim(),
      });

      setEditingId(null);
      await loadMemories();
    } catch (editError) {
      setError(
        editError instanceof Error
          ? editError.message
          : "Could not update memory.",
      );
    }
  };

  const removeMemory = async (memory: Memory) => {
    try {
      await apiDelete(`/api/memories/${memory.id}`);
      await loadMemories();
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Could not delete memory.",
      );
    }
  };

  return (
    <SlideOver
      title="Memory"
      subtitle="What Jarvis remembers across conversations"
      onClose={onClose}
    >
      <div className="memory-create">
        <textarea
          value={newContent}
          onChange={(event) => setNewContent(event.target.value)}
          placeholder="Teach Jarvis something to remember, e.g. 'I prefer concise answers' or 'My physics exam is on Dec 3'."
          rows={3}
        />

        <div className="memory-create-row">
          <select
            value={newCategory}
            onChange={(event) =>
              setNewCategory(event.target.value as (typeof CATEGORIES)[number])
            }
          >
            {CATEGORIES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>

          <button
            className="panel-primary"
            onClick={() => void createMemory()}
            disabled={busy || !newContent.trim()}
          >
            <Plus size={15} />
            Remember
          </button>
        </div>

        {notice && <div className="panel-notice">{notice}</div>}
      </div>

      <div className="panel-toolbar">
        <input
          className="panel-search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search memories..."
        />

        <select
          className="panel-select"
          value={category}
          onChange={(event) => setCategory(event.target.value)}
        >
          <option value="all">All categories</option>
          {CATEGORIES.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>

        <button
          className="icon-button"
          onClick={() => void loadMemories()}
          title="Refresh"
        >
          <RefreshCw size={15} />
        </button>
      </div>

      {error && <div className="voice-error">{error}</div>}

      <div className="memory-list">
        {memories.length === 0 ? (
          <p className="panel-empty">No memories found.</p>
        ) : (
          memories.map((memory) => (
            <div className="memory-card" key={memory.id}>
              <div className="memory-head">
                <span className={`memory-category ${memory.category}`}>
                  <Brain size={12} />
                  {memory.category}
                </span>
                <button
                  className="memory-delete"
                  onClick={() => void removeMemory(memory)}
                  title="Forget this memory"
                >
                  <Trash2 size={14} />
                </button>
              </div>

              {editingId === memory.id ? (
                <>
                  <textarea
                    value={editDraft}
                    onChange={(event) =>
                      setEditDraft(event.target.value)
                    }
                    rows={3}
                    autoFocus
                  />
                  <div className="memory-edit-buttons">
                    <button
                      className="panel-primary small"
                      onClick={() => void saveEdit(memory)}
                    >
                      Save
                    </button>
                    <button
                      className="chip"
                      onClick={() => setEditingId(null)}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <p
                  className="memory-content"
                  onClick={() => {
                    setEditingId(memory.id);
                    setEditDraft(memory.content);
                  }}
                  title="Click to edit"
                >
                  {memory.content}
                </p>
              )}
            </div>
          ))
        )}
      </div>
    </SlideOver>
  );
}
