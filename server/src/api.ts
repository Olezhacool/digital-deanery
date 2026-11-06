// HTTP API мини-приложения (Hono). Каждый запрос проверяет initData → личность Telegram.
import { Hono } from "hono";
import { validateInitData, type TgUser } from "./auth.js";
import * as db from "./db.js";
import { env } from "./env.js";

type Vars = { user: db.UserRow };

export const app = new Hono<{ Variables: Vars }>();

// Заголовок: Authorization: tma <initData>  или  x-init-data: <initData>.
app.use("/api/*", async (c, next) => {
  let tg: TgUser | null = null;

  if (env.dev) {
    const fakeId = Number(c.req.query("tg"));
    if (fakeId) tg = { id: fakeId, first_name: c.req.query("name") ?? "Dev", username: c.req.query("username") };
  }

  if (!tg) {
    const header =
      c.req.header("x-init-data") ?? c.req.header("authorization")?.replace(/^tma\s+/i, "") ?? "";
    tg = validateInitData(header);
  }

  if (!tg) return c.json({ error: "unauthorized" }, 401);

  const role: db.Role = env.adminIds.includes(tg.id) ? "owner" : "student";
  c.set("user", db.upsertUser(tg, role));
  await next();
});

app.get("/api/health", (c) => c.json({ ok: true }));

app.get("/api/me", (c) => c.json(c.get("user")));

app.get("/api/schedule", (c) => c.json(db.getSchedule(c.get("user").id)));

app.get("/api/marks", (c) => c.json(db.getMarks(c.get("user").id)));

app.get("/api/requests", (c) => {
  const u = c.get("user");
  const all = u.role !== "student";
  return c.json({ all, items: db.getRequests(u.id, all) });
});

app.post("/api/requests", async (c) => {
  const u = c.get("user");
  const body = (await c.req.json().catch(() => ({}))) as { type?: string };
  const req = db.createRequest(u.id, body.type ?? "certificate");
  return c.json(req, 201);
});

// Смена статуса заявки — только сотрудник/владелец.
app.post("/api/requests/:id/status", async (c) => {
  const u = c.get("user");
  if (u.role === "student") return c.json({ error: "forbidden" }, 403);
  const id = Number(c.req.param("id"));
  const body = (await c.req.json().catch(() => ({}))) as { status?: string };
  const ok = db.setRequestStatus(id, (body.status ?? "ready") as db.RequestStatus);
  if (!ok) return c.json({ error: "bad_status" }, 400);
  return c.json({ ok: true });
});
