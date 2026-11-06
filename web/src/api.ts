// Клиент API мини-приложения. Личность передаётся заголовком x-init-data.
export interface Profile {
  id: number;
  full_name: string;
  role: "student" | "employee" | "owner";
  faculty: string;
  program: string;
  course: number;
  group_title: string | null;
}
export interface Mark {
  id: number;
  discipline: string;
  teacher: string;
  kind: string;
  value: string;
  term: number;
}
export interface ScheduleItem {
  day: number;
  start: string;
  discipline: string;
  room: string;
  kind: string;
}
export interface RequestItem {
  id: number;
  type: string;
  type_label: string;
  status: "new" | "in_progress" | "ready" | "rejected";
  note: string;
  created_at: string;
}

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:3000";

function initData(): string {
  const tg = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram;
  return tg?.WebApp?.initData ?? "";
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: {
      "x-init-data": initData(),
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return (await r.json()) as T;
}

export const api = {
  me: () => call<Profile>("/api/me"),
  marks: () => call<Mark[]>("/api/marks"),
  schedule: () => call<ScheduleItem[]>("/api/schedule"),
  requests: () => call<{ all: boolean; items: RequestItem[] }>("/api/requests"),
  createRequest: (type: string) =>
    call<RequestItem>("/api/requests", { method: "POST", body: JSON.stringify({ type }) }),
};
