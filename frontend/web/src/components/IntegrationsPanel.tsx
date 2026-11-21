import { useCallback, useEffect, useState } from "react";
import {
  CalendarClock,
  GraduationCap,
  LoaderCircle,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import { SlideOver } from "./SlideOver";
import { apiDelete, apiGet, apiPost } from "../lib/api";

type TelegramStatus = {
  credentials_present: boolean;
  connected: boolean;
  groups: Record<string, string>;
};

type DigestData = {
  announcements: string[];
  assignments: { title: string; details: string; deadline: string | null }[];
  deadlines: { what: string; when: string | null }[];
  important: string[];
  summary: string;
};

type SubjectDigest = {
  messages_read: number;
  error?: string | null;
  data?: DigestData | null;
  raw_summary?: string | null;
};

type DigestResponse = {
  hours: number;
  subjects: Record<string, SubjectDigest>;
};

type CalendarEvent = {
  id?: number;
  title: string;
  start: string;
  end: string;
  source: string;
  notes?: string | null;
};

type PlanBlock = {
  subject?: string;
  task?: string;
  duration_minutes?: number;
  start?: string | null;
  end?: string | null;
};

type StudyPlan = {
  plan_title?: string;
  days?: { date?: string; blocks?: PlanBlock[] }[];
  notes?: string;
};

type IntegrationsPanelProps = {
  onClose: () => void;
};

export function IntegrationsPanel({ onClose }: IntegrationsPanelProps) {
  const [tab, setTab] = useState<"telegram" | "calendar">("telegram");

  // Telegram state
  const [telegramStatus, setTelegramStatus] =
    useState<TelegramStatus | null>(null);
  const [digest, setDigest] = useState<DigestResponse | null>(null);
  const [digestLoading, setDigestLoading] = useState(false);
  const [digestHours, setDigestHours] = useState(24);
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);

  // Calendar state
  const [calendarEvents, setCalendarEvents] = useState<CalendarEvent[]>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventTitle, setEventTitle] = useState("");
  const [eventStart, setEventStart] = useState("");
  const [eventEnd, setEventEnd] = useState("");
  const [eventNotes, setEventNotes] = useState("");
  const [calendarPlan, setCalendarPlan] = useState<StudyPlan | null>(null);
  const [calendarPlanLoading, setCalendarPlanLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const loadTelegramStatus = useCallback(async () => {
    try {
      setTelegramStatus(
        await apiGet<TelegramStatus>("/api/integrations/telegram/status"),
      );
    } catch {
      setTelegramStatus(null);
    }
  }, []);

  const loadCalendarEvents = useCallback(async () => {
    setEventsLoading(true);

    try {
      const data = await apiGet<{ events: CalendarEvent[] }>(
        "/api/integrations/calendar/upcoming?days=14",
      );

      setCalendarEvents(data.events);
      setError(null);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Could not load calendar.",
      );
    } finally {
      setEventsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTelegramStatus();
    void loadCalendarEvents();
  }, [loadTelegramStatus, loadCalendarEvents]);

  const fetchDigest = async () => {
    setDigestLoading(true);
    setError(null);
    setDigest(null);
    setPlan(null);

    try {
      const data = await apiGet<DigestResponse>(
        `/api/integrations/telegram/digest?hours=${digestHours}`,
      );

      setDigest(data);
    } catch (digestError) {
      setError(
        digestError instanceof Error
          ? digestError.message
          : "Digest failed.",
      );
    } finally {
      setDigestLoading(false);
    }
  };

  const fetchTelegramPlan = async () => {
    setPlanLoading(true);
    setError(null);
    setPlan(null);

    try {
      const data = await apiGet<{
        plan: StudyPlan | null;
        raw_plan: string | null;
      }>(
        `/api/integrations/telegram/plan?kind=weekly&days=7&hours=${digestHours}`,
      );

      if (data.plan) {
        setPlan(data.plan);
      } else if (data.raw_plan) {
        setError("The planner returned unstructured text.");
      }
    } catch (planError) {
      setError(
        planError instanceof Error ? planError.message : "Plan failed.",
      );
    } finally {
      setPlanLoading(false);
    }
  };

  const createEvent = async () => {
    if (!eventTitle.trim() || !eventStart || !eventEnd) {
      setError("Event needs a title, start, and end.");
      return;
    }

    setError(null);

    try {
      await apiPost("/api/integrations/calendar/events", {
        title: eventTitle.trim(),
        start: eventStart,
        end: eventEnd,
        notes: eventNotes.trim() || null,
      });

      setEventTitle("");
      setEventStart("");
      setEventEnd("");
      setEventNotes("");
      await loadCalendarEvents();
    } catch (createError) {
      setError(
        createError instanceof Error
          ? createError.message
          : "Could not create event.",
      );
    }
  };

  const deleteEvent = async (event: CalendarEvent) => {
    if (!event.id) {
      return;
    }

    try {
      await apiDelete(`/api/integrations/calendar/events/${event.id}`);
      await loadCalendarEvents();
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "Could not delete event.",
      );
    }
  };

  const buildCalendarPlan = async () => {
    setCalendarPlanLoading(true);
    setError(null);
    setCalendarPlan(null);

    try {
      const data = await apiGet<{
        plan: StudyPlan | null;
        raw_plan: string | null;
      }>("/api/integrations/calendar/study-plan?days=7");

      if (data.plan) {
        setCalendarPlan(data.plan);
      }
    } catch (planError) {
      setError(
        planError instanceof Error ? planError.message : "Plan failed.",
      );
    } finally {
      setCalendarPlanLoading(false);
    }
  };

  const formatTimestamp = (value: string) => {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <SlideOver
      title="Integrations"
      subtitle="Telegram study groups and calendar"
      onClose={onClose}
    >
      <div className="chip-row tabs">
        <button
          className={`chip ${tab === "telegram" ? "active" : ""}`}
          onClick={() => setTab("telegram")}
        >
          <Send size={13} />
          Telegram
        </button>
        <button
          className={`chip ${tab === "calendar" ? "active" : ""}`}
          onClick={() => setTab("calendar")}
        >
          <CalendarClock size={13} />
          Calendar
        </button>
      </div>

      {error && <div className="voice-error">{error}</div>}

      {tab === "telegram" && (
        <div className="integration-section">
          <div className="integration-status">
            <span
              className={`status-dot ${
                telegramStatus?.connected ? "ok" : ""
              }`}
            />
            {telegramStatus?.credentials_present
              ? telegramStatus.connected
                ? "Connected (read-only)"
                : "Configured, not connected"
              : "Not configured — run scripts/telegram_login.py"}
          </div>

          <div className="panel-toolbar">
            <label className="panel-inline-label">
              Look back
              <select
                className="panel-select"
                value={digestHours}
                onChange={(event) =>
                  setDigestHours(Number(event.target.value))
                }
              >
                <option value={12}>12 hours</option>
                <option value={24}>24 hours</option>
                <option value={48}>2 days</option>
                <option value={72}>3 days</option>
                <option value={168}>1 week</option>
              </select>
            </label>

            <button
              className="panel-primary"
              onClick={() => void fetchDigest()}
              disabled={digestLoading}
            >
              {digestLoading ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <RefreshCw size={15} />
              )}
              Summarize groups
            </button>

            <button
              className="panel-secondary"
              onClick={() => void fetchTelegramPlan()}
              disabled={planLoading}
            >
              {planLoading ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <GraduationCap size={15} />
              )}
              Build study plan
            </button>
          </div>

          {digest &&
            Object.entries(digest.subjects).map(([subject, subjectData]) => (
              <div className="digest-card" key={subject}>
                <h3 className="digest-subject">{subject}</h3>
                <span className="digest-meta">
                  {subjectData.messages_read} messages read
                </span>

                {subjectData.error && (
                  <p className="digest-error">{subjectData.error}</p>
                )}

                {subjectData.data && (
                  <>
                    {subjectData.data.summary && (
                      <p className="digest-summary">
                        {subjectData.data.summary}
                      </p>
                    )}

                    {subjectData.data.announcements.length > 0 && (
                      <div className="digest-group">
                        <span className="digest-label">ANNOUNCEMENTS</span>
                        <ul>
                          {subjectData.data.announcements.map(
                            (item, index) => (
                              <li key={index}>{item}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}

                    {subjectData.data.assignments.length > 0 && (
                      <div className="digest-group">
                        <span className="digest-label">ASSIGNMENTS</span>
                        <ul>
                          {subjectData.data.assignments.map(
                            (assignment, index) => (
                              <li key={index}>
                                <strong>{assignment.title}</strong>
                                {assignment.deadline && (
                                  <> — due {assignment.deadline}</>
                                )}
                                {assignment.details && (
                                  <span className="digest-detail">
                                    {assignment.details}
                                  </span>
                                )}
                              </li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}

                    {subjectData.data.deadlines.length > 0 && (
                      <div className="digest-group">
                        <span className="digest-label">DEADLINES</span>
                        <ul>
                          {subjectData.data.deadlines.map(
                            (deadline, index) => (
                              <li key={index}>
                                {deadline.what}
                                {deadline.when && (
                                  <> — {deadline.when}</>
                                )}
                              </li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}

                    {subjectData.data.important.length > 0 && (
                      <div className="digest-group">
                        <span className="digest-label">IMPORTANT</span>
                        <ul>
                          {subjectData.data.important.map(
                            (item, index) => (
                              <li key={index}>{item}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                  </>
                )}

                {subjectData.raw_summary && (
                  <p className="digest-raw">{subjectData.raw_summary}</p>
                )}
              </div>
            ))}

          {plan && (
            <div className="digest-card">
              <h3 className="digest-subject">
                {plan.plan_title ?? "Study plan"}
              </h3>

              {plan.days?.map((day, dayIndex) => (
                <div className="plan-day" key={dayIndex}>
                  <span className="plan-date">{day.date}</span>
                  <ul>
                    {day.blocks?.map((block, blockIndex) => (
                      <li key={blockIndex}>
                        {block.start && block.end && (
                          <span className="plan-time">
                            {block.start}–{block.end}
                          </span>
                        )}
                        <strong>{block.subject}</strong>{" "}
                        {block.task}
                        {block.duration_minutes && (
                          <span className="plan-duration">
                            {" "}
                            ({block.duration_minutes} min)
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}

              {plan.notes && <p className="digest-summary">{plan.notes}</p>}
            </div>
          )}
        </div>
      )}

      {tab === "calendar" && (
        <div className="integration-section">
          <div className="panel-toolbar">
            <button
              className="panel-primary"
              onClick={() => void loadCalendarEvents()}
              disabled={eventsLoading}
            >
              {eventsLoading ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <RefreshCw size={15} />
              )}
              Refresh
            </button>

            <button
              className="panel-secondary"
              onClick={() => void buildCalendarPlan()}
              disabled={calendarPlanLoading}
            >
              {calendarPlanLoading ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <GraduationCap size={15} />
              )}
              Plan from calendar
            </button>
          </div>

          <div className="event-create">
            <span className="digest-label">ADD LOCAL EVENT</span>
            <input
              value={eventTitle}
              onChange={(event) => setEventTitle(event.target.value)}
              placeholder="Event title"
            />
            <div className="event-create-row">
              <label>
                Start
                <input
                  type="datetime-local"
                  value={eventStart}
                  onChange={(event) => setEventStart(event.target.value)}
                />
              </label>
              <label>
                End
                <input
                  type="datetime-local"
                  value={eventEnd}
                  onChange={(event) => setEventEnd(event.target.value)}
                />
              </label>
            </div>
            <input
              value={eventNotes}
              onChange={(event) => setEventNotes(event.target.value)}
              placeholder="Notes (optional)"
            />
            <button
              className="panel-primary"
              onClick={() => void createEvent()}
              disabled={!eventTitle.trim() || !eventStart || !eventEnd}
            >
              Add event
            </button>
          </div>

          <div className="event-list">
            {calendarEvents.length === 0 ? (
              <p className="panel-empty">
                No upcoming events in the next 14 days.
              </p>
            ) : (
              calendarEvents.map((event, index) => (
                <div className="event-card" key={`${event.title}-${index}`}>
                  <div className="event-main">
                    <span className="event-title">{event.title}</span>
                    <span className="event-time">
                      {formatTimestamp(event.start)} →{" "}
                      {formatTimestamp(event.end)}
                    </span>
                    {event.notes && (
                      <span className="event-notes">{event.notes}</span>
                    )}
                  </div>
                  <span className={`event-source ${event.source}`}>
                    {event.source}
                  </span>
                  {event.source === "local" && event.id && (
                    <button
                      className="memory-delete"
                      onClick={() => void deleteEvent(event)}
                      title="Delete event"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))
            )}
          </div>

          {calendarPlan && (
            <div className="digest-card">
              <h3 className="digest-subject">
                {calendarPlan.plan_title ?? "Calendar study plan"}
              </h3>

              {calendarPlan.days?.map((day, dayIndex) => (
                <div className="plan-day" key={dayIndex}>
                  <span className="plan-date">{day.date}</span>
                  <ul>
                    {day.blocks?.map((block, blockIndex) => (
                      <li key={blockIndex}>
                        {block.start && block.end && (
                          <span className="plan-time">
                            {block.start}–{block.end}
                          </span>
                        )}
                        <strong>{block.subject}</strong> {block.task}
                        {block.duration_minutes && (
                          <span className="plan-duration">
                            {" "}
                            ({block.duration_minutes} min)
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}

              {calendarPlan.notes && (
                <p className="digest-summary">{calendarPlan.notes}</p>
              )}
            </div>
          )}
        </div>
      )}
    </SlideOver>
  );
}
