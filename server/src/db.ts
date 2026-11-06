// Хранилище: SQLite через встроенный node:sqlite (без нативных зависимостей).
// Схема + каталог (группы/дисциплины/расписание) + демо-данные на пользователя.
import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import path from "node:path";
import type { TgUser } from "./auth.js";

export type Role = "student" | "employee" | "owner";
export type RequestStatus = "new" | "in_progress" | "ready" | "rejected";

export interface UserRow {
  id: number;
  tg_id: number;
  full_name: string;
  role: Role;
  faculty: string;
  program: string;
  course: number;
  group_id: number | null;
  group_title: string | null;
}
export interface MarkRow {
  id: number;
  discipline: string;
  teacher: string;
  kind: string;
  value: string;
  term: number;
}
export interface RequestRow {
  id: number;
  type: string;
  type_label: string;
  status: RequestStatus;
  note: string;
  created_at: string;
}
export interface ScheduleRow {
  day: number;
  start: string;
  discipline: string;
  room: string;
  kind: string;
}

const dataDir = path.resolve(process.cwd(), "data");
mkdirSync(dataDir, { recursive: true });
export const db = new DatabaseSync(path.join(dataDir, "deanery.db"));

db.exec(`
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER UNIQUE NOT NULL,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'student',
  faculty TEXT NOT NULL DEFAULT 'Институт цифровых технологий',
  program TEXT NOT NULL DEFAULT 'Прикладная информатика',
  course INTEGER NOT NULL DEFAULT 2,
  group_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS disciplines (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  teacher TEXT NOT NULL,
  group_id INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS marks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  discipline_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  term INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new',
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS schedule (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_id INTEGER NOT NULL,
  day INTEGER NOT NULL,
  start TEXT NOT NULL,
  discipline_id INTEGER NOT NULL,
  room TEXT NOT NULL,
  kind TEXT NOT NULL
);
`);

const REQUEST_LABELS: Record<string, string> = {
  certificate: "Справка об обучении",
  transcript: "Копия зачётной книжки",
  academic: "Академическая справка",
};

// --- Каталог (вымышленные данные, idempotent) ---
const groupsCount = (db.prepare("SELECT COUNT(*) AS n FROM groups").get() as { n: number }).n;
if (groupsCount === 0) {
  const seed = db.exec(`
    INSERT INTO groups (title) VALUES ('ИС-31'), ('ПГС-21');
    INSERT INTO disciplines (title, teacher, group_id) VALUES
      ('Базы данных', 'Соколова А.В.', 1),
      ('Программная инженерия', 'Гусев Д.М.', 1),
      ('Компьютерные сети', 'Фролов П.С.', 1),
      ('Строительная механика', 'Андреева Е.И.', 2),
      ('Железобетонные конструкции', 'Ковалёв И.Г.', 2),
      ('Геодезия', 'Морозова Т.А.', 2);
    INSERT INTO schedule (group_id, day, start, discipline_id, room, kind) VALUES
      (1, 1, '09:00', 1, 'К-405', 'лекция'),
      (1, 1, '10:45', 2, 'К-407', 'практика'),
      (1, 3, '09:00', 3, 'Л-112', 'лекция'),
      (1, 4, '12:30', 2, 'К-407', 'лабораторная'),
      (2, 1, '09:00', 4, 'К-210', 'лекция'),
      (2, 2, '10:45', 5, 'К-215', 'практика'),
      (2, 3, '09:00', 6, 'Пол-1', 'практика');
  `);
}

// Детерминированные оценки по дисциплине (по id), чтобы демо было стабильным.
const MARKS_BY_DISCIPLINE: Record<number, Array<{ kind: string; value: string; term: number }>> = {
  1: [
    { kind: "экзамен", value: "4", term: 3 },
    { kind: "курсовая", value: "5", term: 3 },
  ],
  2: [{ kind: "зачёт", value: "зачёт", term: 2 }],
  3: [{ kind: "экзамен", value: "3", term: 1 }],
  4: [{ kind: "экзамен", value: "5", term: 3 }],
  5: [{ kind: "курсовая", value: "4", term: 3 }],
  6: [{ kind: "зачёт", value: "незачёт", term: 2 }],
};

function pickGroupId(): number {
  const rows = db.prepare("SELECT id FROM groups ORDER BY id").all() as Array<{ id: number }>;
  return rows.length ? rows[0].id : 1;
}

function ensureUserData(userId: number, groupId: number): void {
  const has = (db.prepare("SELECT COUNT(*) AS n FROM marks WHERE user_id = ?").get(userId) as { n: number }).n;
  if (has > 0) return;

  const disciplines = db
    .prepare("SELECT id FROM disciplines WHERE group_id = ? ORDER BY id")
    .all(groupId) as Array<{ id: number }>;

  for (const d of disciplines) {
    for (const m of MARKS_BY_DISCIPLINE[d.id] ?? []) {
      db.prepare("INSERT INTO marks (user_id, discipline_id, kind, value, term) VALUES (?,?,?,?,?)")
        .run(userId, d.id, m.kind, m.value, m.term);
    }
  }

  db.prepare("INSERT INTO requests (user_id, type, status) VALUES (?, 'certificate', 'ready')").run(userId);
  db.prepare("INSERT INTO requests (user_id, type, status) VALUES (?, 'academic', 'in_progress')").run(userId);
}

export function upsertUser(tg: TgUser, role: Role): UserRow {
  const existing = db.prepare("SELECT * FROM users WHERE tg_id = ?").get(tg.id) as UserRow | undefined;
  if (existing) {
    if (existing.role !== role) {
      db.prepare("UPDATE users SET role = ? WHERE id = ?").run(role, existing.id);
    }
    return withGroup({ ...existing, role });
  }

  const groupId = pickGroupId();
  const full = [tg.first_name, tg.last_name].filter(Boolean).join(" ") || "Студент";
  const info = db
    .prepare("INSERT INTO users (tg_id, full_name, role, group_id) VALUES (?,?,?,?)")
    .run(tg.id, full, role, groupId);
  const userId = Number(info.lastInsertRowid);
  ensureUserData(userId, groupId);
  return withGroup(db.prepare("SELECT * FROM users WHERE id = ?").get(userId) as unknown as UserRow);
}

function withGroup(u: UserRow): UserRow {
  const g = u.group_id ? (db.prepare("SELECT title FROM groups WHERE id = ?").get(u.group_id) as { title: string } | undefined) : undefined;
  return { ...u, group_title: g?.title ?? null };
}

export function getProfile(userId: number): UserRow {
  return withGroup(db.prepare("SELECT * FROM users WHERE id = ?").get(userId) as unknown as UserRow);
}

export function getMarks(userId: number): MarkRow[] {
  return db
    .prepare(
      `SELECT m.id, d.title AS discipline, d.teacher, m.kind, m.value, m.term
       FROM marks m JOIN disciplines d ON d.id = m.discipline_id
       WHERE m.user_id = ? ORDER BY m.term DESC, d.title`
    )
    .all(userId) as unknown as MarkRow[];
}

export function getSchedule(userId: number): ScheduleRow[] {
  const u = getProfile(userId);
  if (!u.group_id) return [];
  return db
    .prepare(
      `SELECT s.day, s.start, d.title AS discipline, s.room, s.kind
       FROM schedule s JOIN disciplines d ON d.id = s.discipline_id
       WHERE s.group_id = ? ORDER BY s.day, s.start`
    )
    .all(u.group_id) as unknown as ScheduleRow[];
}

export function getRequests(userId: number, all: boolean): RequestRow[] {
  const base = `SELECT r.id, r.type, r.status, r.note, r.created_at
                FROM requests r ${all ? "" : "WHERE r.user_id = ?"}
                ORDER BY r.id DESC`;
  const rows = (all ? db.prepare(base).all() : db.prepare(base).all(userId)) as Array<{
    id: number; type: string; status: RequestStatus; note: string | null; created_at: string;
  }>;
  return rows.map((r) => ({ ...r, note: r.note ?? "", type_label: REQUEST_LABELS[r.type] ?? r.type }));
}

export function createRequest(userId: number, type: string): RequestRow {
  const t = type in REQUEST_LABELS ? type : "certificate";
  const info = db.prepare("INSERT INTO requests (user_id, type) VALUES (?, ?)").run(userId, t);
  return getRequests(userId, false)[0];
}

export function setRequestStatus(id: number, status: RequestStatus): boolean {
  if (!["new", "in_progress", "ready", "rejected"].includes(status)) return false;
  const info = db.prepare("UPDATE requests SET status = ? WHERE id = ?").run(status, id);
  return Number(info.changes) > 0;
}
