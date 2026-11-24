// קריאות ל-API של DayPilot. כל הזמנים מגיעים ב-ISO (UTC) ומוצגים בשעון ישראל.

export type TaskType = "scheduled" | "open" | "recurring";

export interface TaskView {
  id: number;
  title: string;
  task_type: TaskType;
  status: "active" | "done" | "cancelled";
  importance: number;
  work_style: "assignment" | "exam";
  deadline: string | null;
  estimated_minutes: number | null;
  remaining_minutes: number | null;
  scheduled_minutes: number;
  done_minutes: number;
  postponed_count: number;
  recurrence_rule: string | null;
  assumptions: string[];
}

export interface SessionItem {
  id: number;
  task_id: number;
  task_title: string;
  start: string;
  end: string;
  status: string;
  locked?: boolean;
}

export interface CalendarDay {
  date: string;
  weekday: number;
  hebrew_date: string;
  holiday: string | null;
  is_rest_day: boolean;
  is_chol_hamoed: boolean;
}

export interface CalendarBlock {
  start: string;
  end: string;
  kind: "rest" | "class" | "work" | "commitment" | "blocked" | "event";
  label: string;
}

export interface CalendarData {
  days: CalendarDay[];
  blocks: CalendarBlock[];
  sessions: SessionItem[];
}

export interface Dashboard {
  today: string;
  hebrew_date: string;
  hebrew_date_tonight: string | null;
  unreported_sessions: { id: number; task_id: number; task_title: string; start: string; end: string }[];
  today_sessions: SessionItem[];
  week: { date: string; weekday: number; minutes: number; is_rest_day: boolean; holiday: string | null }[];
  daily_max_minutes: number;
  upcoming_deadlines: TaskView[];
  needs_scheduling: TaskView[];
  idle_open_tasks: TaskView[];
  overloaded_days: string[];
  counts: { active: number; scheduled: number; open: number; recurring: number };
}

export interface Progress {
  days: number;
  daily_minutes: { date: string; minutes: number }[];
  total_minutes: number;
  sessions_done: number;
  sessions_missed: number;
  completion_rate: number | null;
  tasks: {
    id: number;
    title: string;
    status: string;
    deadline: string | null;
    estimated_minutes: number;
    done_minutes: number;
    remaining_minutes: number;
    scheduled_minutes: number;
    postponed_count: number;
  }[];
  tasks_completed: number;
}

export interface Rule {
  id: number;
  weekday: number;
  start_time: string;
  end_time: string;
  kind: string;
  label: string;
}

export interface Me {
  id: number;
  name: string;
  ui_language: "he" | "en";
  city: string | null;
  cities: { key: string; name_he: string; name_en: string }[];
  preferences: {
    min_session_minutes: number;
    max_session_minutes: number;
    daily_max_minutes: number;
    shabbat_buffer_minutes: number;
    block_chol_hamoed: boolean;
  };
  rules: Rule[];
}

export interface Approval {
  type: "proposal_approval";
  display: string;
  question: string;
  actions: string[];
  proposal: {
    id: string;
    kind: string;
    summary: string;
    feasible: boolean;
    add_sessions: { task_id: number; start: string; end: string }[];
    remove_session_ids: number[];
    conflicts: { kind: string; task_ids: number[]; message: string; details: Record<string, unknown> }[];
    alternatives: { key: string; description: string; resolves: boolean; missing_minutes: number }[];
  };
}

export interface Turn {
  thread_id: string;
  reply: string | null;
  approval: Approval | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    });
  } catch {
    throw new ApiError("server_unreachable", 0, "server_unreachable");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail && typeof body.detail === "object" ? body.detail : body;
    throw new ApiError(detail.error || response.statusText, response.status, detail.code);
  }
  return body as T;
}

export const api = {
  shutdown: () => request<{ ok: boolean }>("/api/system/shutdown", { method: "POST", headers: { "X-DayPilot": "1" } }),
  me: () => request<Me>("/api/me"),
  updateSettings: (data: Partial<Me["preferences"]> & { city_key?: string; ui_language?: string }) =>
    request<Me>("/api/settings", { method: "PATCH", body: JSON.stringify(data) }),
  addRule: (rule: Omit<Rule, "id">) => request<{ id: number }>("/api/settings/rules", { method: "POST", body: JSON.stringify(rule) }),
  deleteRule: (id: number) => request<{ ok: boolean }>(`/api/settings/rules/${id}`, { method: "DELETE" }),
  tasks: (includeDone = false) => request<TaskView[]>(`/api/tasks?include_done=${includeDone}`),
  calendar: (start: string, end: string) => request<CalendarData>(`/api/calendar?start=${start}&end=${end}`),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  progress: (days = 14) => request<Progress>(`/api/progress?days=${days}`),
  threads: () => request<{ id: string; title: string; updated_at: string }[]>("/api/chat/threads"),
  newThread: () => request<{ id: string }>("/api/chat/threads", { method: "POST" }),
  thread: (id: string) => request<{ id: string; messages: ChatMessage[]; approval: Approval | null }>(`/api/chat/threads/${id}`),
  send: (id: string, text: string) =>
    request<Turn>(`/api/chat/threads/${id}/messages`, { method: "POST", body: JSON.stringify({ text }) }),
  decide: (id: string, action: "approve" | "reject" | "revise", feedback = "") =>
    request<Turn>(`/api/chat/threads/${id}/decision`, { method: "POST", body: JSON.stringify({ action, feedback }) }),
  deleteThread: (id: string) => request<{ ok: boolean }>(`/api/chat/threads/${id}`, { method: "DELETE" }),
};
