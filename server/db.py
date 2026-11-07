"""SQLite: схема и тонкая обёртка над запросами."""
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  login TEXT UNIQUE NOT NULL,
  pass_salt TEXT NOT NULL,
  pass_hash TEXT NOT NULL,
  full_name TEXT NOT NULL,
  faculty TEXT NOT NULL,
  program TEXT NOT NULL,
  course INTEGER NOT NULL,
  group_name TEXT NOT NULL,
  record_book TEXT NOT NULL,
  email TEXT NOT NULL,
  notify INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_name TEXT NOT NULL,
  weekday INTEGER NOT NULL,
  parity TEXT NOT NULL DEFAULT 'all',
  n INTEGER NOT NULL,
  start TEXT NOT NULL,
  end TEXT NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  room TEXT NOT NULL,
  teacher TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lessons_group ON lessons(group_name, weekday);

CREATE TABLE IF NOT EXISTS subjects(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  teacher TEXT NOT NULL,
  credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS grades(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  subject_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  value TEXT NOT NULL,
  graded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grades_user ON grades(user_id);

CREATE TABLE IF NOT EXISTS exams(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_name TEXT NOT NULL,
  date TEXT NOT NULL,
  time TEXT NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  room TEXT NOT NULL,
  teacher TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assignments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL,
  group_name TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  due_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS submissions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'todo',
  submitted_at TEXT,
  UNIQUE(assignment_id, user_id)
);

CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  number TEXT NOT NULL,
  kind TEXT NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'new',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_user ON requests(user_id);

CREATE TABLE IF NOT EXISTS announcements(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tag TEXT NOT NULL DEFAULT 'Деканат',
  created_at TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def q(self, sql, args=()):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    async def one(self, sql, args=()):
        rows = await self.q(sql, args)
        return rows[0] if rows else None

    async def x(self, sql, args=()):
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.lastrowid
