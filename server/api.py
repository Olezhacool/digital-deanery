"""HTTP-API кабинета и раздача веб-приложения."""
from datetime import date, datetime, timedelta

from aiohttp import web

from . import ai
from .auth import SESSION_TTL, make_session, read_session, verify_password

COOKIE = "dd_session"
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
STATUS_LABELS = {"new": "Новая", "in_progress": "В работе", "ready": "Готова", "rejected": "Отклонена"}
REQUEST_KINDS = ["Справка об обучении", "Справка в военкомат", "Справка для стипендии",
                 "Копия зачётной книжки", "Академическая справка"]


def err(message: str, status: int = 400):
    return web.json_response({"error": message}, status=status)


def iso_minutes(value: str) -> datetime:
    return datetime.fromisoformat(value)


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def build_app(cfg, db) -> web.Application:
    def today() -> date:
        return datetime.now(cfg.tz).date()

    def parity(d: date) -> str:
        week = (d - cfg.semester_start).days // 7 + 1
        return "even" if week % 2 == 0 else "odd"

    def week_number(d: date) -> int:
        return (d - cfg.semester_start).days // 7 + 1

    async def lessons_for(group: str, d: date) -> list:
        rows = await db.q(
            "SELECT n,start,end,title,kind,room,teacher FROM lessons "
            "WHERE group_name=? AND weekday=? AND parity IN ('all', ?) ORDER BY start",
            (group, d.weekday() + 1, parity(d)),
        )
        return [dict(r) for r in rows]

    async def week_payload(group: str, offset: int) -> dict:
        t = today()
        monday = t - timedelta(days=t.weekday()) + timedelta(weeks=offset)
        days = {}
        for i in range(6):
            d = monday + timedelta(days=i)
            days[str(i + 1)] = await lessons_for(group, d)
        return {
            "number": week_number(monday),
            "parity": "чётная" if parity(monday) == "even" else "нечётная",
            "monday": monday.isoformat(),
            "days": days,
            "today": t.weekday(),
        }

    async def grades_payload(user_id: int, group: str) -> dict:
        rows = await db.q(
            "SELECT s.id,s.name,s.teacher,s.credits,g.kind,g.value,g.graded_at "
            "FROM subjects s LEFT JOIN grades g ON g.subject_id=s.id AND g.user_id=? "
            "WHERE s.id IN (SELECT subject_id FROM assignments WHERE group_name=?) "
            "OR s.id IN (SELECT subject_id FROM grades WHERE user_id=?) "
            "ORDER BY s.name",
            (user_id, group, user_id),
        )
        subjects: dict[int, dict] = {}
        for r in rows:
            s = subjects.setdefault(r["id"], {"id": r["id"], "name": r["name"], "teacher": r["teacher"],
                                              "credits": r["credits"], "grades": []})
            if r["kind"]:
                s["grades"].append({"kind": r["kind"], "value": r["value"], "date": r["graded_at"]})

        numeric = []
        debts = []
        for s in subjects.values():
            for g in s["grades"]:
                if g["value"].isdigit():
                    numeric.append(int(g["value"]))
                elif g["value"] == "Незачёт":
                    debts.append(s["name"])
        avg = round(sum(numeric) / len(numeric), 2) if numeric else 0
        exams = await db.q("SELECT date,time,title,kind,room,teacher FROM exams "
                           "WHERE group_name=? AND date>=? ORDER BY date", (group, today().isoformat()))
        return {
            "subjects": list(subjects.values()),
            "stats": {"avg": avg, "debts": len(set(debts)), "subjects": len(subjects),
                      "credits": sum(s["credits"] for s in subjects.values())},
            "debt_names": sorted(set(debts)),
            "exams": [dict(e) for e in exams],
        }

    async def assignments_payload(user_id: int, group: str) -> list:
        rows = await db.q(
            "SELECT a.id,a.title,a.description,a.due_at,s.name subject,"
            "COALESCE(sub.status,'todo') status, sub.submitted_at "
            "FROM assignments a JOIN subjects s ON s.id=a.subject_id "
            "LEFT JOIN submissions sub ON sub.assignment_id=a.id AND sub.user_id=? "
            "WHERE a.group_name=? ORDER BY a.due_at",
            (user_id, group),
        )
        out = []
        for r in rows:
            due = iso_minutes(r["due_at"])
            days = (due.date() - today()).days
            out.append({"id": r["id"], "title": r["title"], "description": r["description"],
                        "subject": r["subject"], "due_at": r["due_at"], "status": r["status"],
                        "due_label": f"{due.day} {MONTHS[due.month - 1]}",
                        "days_left": days})
        return out

    async def requests_payload(user_id: int) -> list:
        rows = await db.q("SELECT * FROM requests WHERE user_id=? ORDER BY id DESC", (user_id,))
        return [{"id": r["id"], "number": r["number"], "kind": r["kind"], "comment": r["comment"],
                 "status": r["status"], "status_label": STATUS_LABELS.get(r["status"], r["status"]),
                 "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]

    async def announcements_payload() -> list:
        rows = await db.q("SELECT * FROM announcements ORDER BY id DESC LIMIT 10")
        return [{"id": r["id"], "title": r["title"], "body": r["body"], "tag": r["tag"],
                 "created_at": r["created_at"]} for r in rows]

    def me_payload(u) -> dict:
        return {"name": u["full_name"], "first_name": u["full_name"].split()[1],
                "letter": u["full_name"][0].upper(), "login": u["login"],
                "faculty": u["faculty"], "program": u["program"], "course": u["course"],
                "group": u["group_name"], "record_book": u["record_book"],
                "email": u["email"], "notify": bool(u["notify"])}

    @web.middleware
    async def security_mw(request, handler):
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        return response

    @web.middleware
    async def auth_mw(request, handler):
        request["user"] = None
        if request.path.startswith("/api/"):
            token = request.cookies.get(COOKIE, "")
            user_id = read_session(token, cfg.secret)
            if user_id:
                request["user"] = await db.one("SELECT * FROM users WHERE id=?", (user_id,))
            if request.path == "/api/login":
                return await handler(request)
            if not request["user"]:
                return err("Войдите в кабинет", 401)
        return await handler(request)

    async def body(request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # ---------- авторизация
    async def login(request):
        data = await body(request)
        login_name = str(data.get("login", "")).strip().lower()
        password = str(data.get("password", ""))
        user = await db.one("SELECT * FROM users WHERE login=?", (login_name,))
        # Сравниваем хеш даже для несуществующего логина: одинаковое время ответа.
        salt = user["pass_salt"] if user else "00" * 16
        digest = user["pass_hash"] if user else "00" * 32
        ok = verify_password(password, salt, digest) and user is not None
        if not ok:
            return err("Неверный логин или пароль", 401)
        response = web.json_response({"ok": True})
        response.set_cookie(COOKIE, make_session(user["id"], cfg.secret), httponly=True,
                            samesite="Lax", secure=cfg.cookie_secure, max_age=SESSION_TTL, path="/")
        return response

    async def logout(request):
        response = web.json_response({"ok": True})
        response.del_cookie(COOKIE, path="/")
        return response

    # ---------- данные кабинета
    async def bootstrap(request):
        u = request["user"]
        group = u["group_name"]
        week = await week_payload(group, 0)
        grades = await grades_payload(u["id"], group)
        assignments = await assignments_payload(u["id"], group)
        requests = await requests_payload(u["id"])

        t = today()
        now_minutes = datetime.now(cfg.tz).hour * 60 + datetime.now(cfg.tz).minute
        today_lessons = week["days"][str(t.weekday() + 1)] if t.weekday() < 6 else []
        next_lesson = None
        for lesson in today_lessons:
            h, m = map(int, lesson["start"].split(":"))
            delta = h * 60 + m - now_minutes
            if delta > 0:
                next_lesson = dict(lesson, in_min=delta)
                break

        tomorrow = t + timedelta(days=1)
        return web.json_response({
            "me": me_payload(u),
            "today": {"iso": t.isoformat(), "weekday": t.weekday()},
            "week": week,
            "grades": grades,
            "assignments": assignments,
            "requests": requests,
            "announcements": await announcements_payload(),
            "next": next_lesson,
            "today_lessons": today_lessons,
        })

    async def schedule_week(request):
        u = request["user"]
        try:
            offset = max(-30, min(30, int(request.query.get("offset", 0))))
        except ValueError:
            offset = 0
        return web.json_response(await week_payload(u["group_name"], offset))

    async def create_request(request):
        u = request["user"]
        data = await body(request)
        kind = str(data.get("kind", "")).strip()
        comment = str(data.get("comment", "")).strip()[:500]
        if kind not in REQUEST_KINDS:
            return err("Выберите тип заявки")
        now = datetime.now(cfg.tz).isoformat(timespec="minutes")
        new_id = await db.x(
            "INSERT INTO requests(user_id,number,kind,comment,status,created_at,updated_at) "
            "VALUES(?,?,?,?, 'new', ?, ?)", (u["id"], "—", kind, comment, now, now),
        )
        await db.x("UPDATE requests SET number=? WHERE id=?", (f"Д-{new_id:04d}", new_id))
        return web.json_response({"requests": await requests_payload(u["id"])})

    async def request_detail(request):
        u = request["user"]
        try:
            rid = int(request.match_info["id"])
        except ValueError:
            return err("Заявка не найдена", 404)
        row = await db.one("SELECT * FROM requests WHERE id=? AND user_id=?", (rid, u["id"]))
        if not row:
            return err("Заявка не найдена", 404)
        return web.json_response({"id": row["id"], "number": row["number"], "kind": row["kind"],
                                  "comment": row["comment"], "status": row["status"],
                                  "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                                  "created_at": row["created_at"], "updated_at": row["updated_at"]})

    async def submit_assignment(request):
        u = request["user"]
        try:
            aid = int(request.match_info["id"])
        except ValueError:
            return err("Задание не найдено", 404)
        owned = await db.one(
            "SELECT 1 FROM assignments WHERE id=? AND group_name=?", (aid, u["group_name"]))
        if not owned:
            return err("Задание не найдено", 404)
        now = datetime.now(cfg.tz).isoformat(timespec="minutes")
        await db.x(
            "INSERT INTO submissions(assignment_id,user_id,status,submitted_at) VALUES(?,?,'submitted',?) "
            "ON CONFLICT(assignment_id,user_id) DO UPDATE SET status='submitted', submitted_at=excluded.submitted_at",
            (aid, u["id"], now),
        )
        return web.json_response({"assignments": await assignments_payload(u["id"], u["group_name"])})

    async def ask_ai(request):
        u = request["user"]
        question = str((await body(request)).get("question", ""))[:500]
        grades = await grades_payload(u["id"], u["group_name"])
        assignments = await assignments_payload(u["id"], u["group_name"])
        requests = await requests_payload(u["id"])
        t = today()
        now = datetime.now(cfg.tz)
        week = await week_payload(u["group_name"], 0)
        today_lessons = week["days"][str(t.weekday() + 1)] if t.weekday() < 6 else []
        tomorrow_lessons = week["days"][str((t + timedelta(days=1)).weekday() + 1)] \
            if (t + timedelta(days=1)).weekday() < 6 else []
        next_lesson = None
        for lesson in today_lessons:
            h, m = map(int, lesson["start"].split(":"))
            delta = h * 60 + m - (now.hour * 60 + now.minute)
            if delta > 0:
                next_lesson = dict(lesson, in_min=delta)
                break
        exams = [f"{e['title']} — {e['date']}" for e in grades["exams"][:3]]
        ctx = {
            "first_name": u["full_name"].split()[1],
            "today_lessons": today_lessons,
            "tomorrow_lessons": tomorrow_lessons,
            "today_label": f"{t.day} {MONTHS[t.month - 1]}",
            "tomorrow_label": f"{(t + timedelta(days=1)).day} {MONTHS[(t + timedelta(days=1)).month - 1]}",
            "next_lesson": next_lesson,
            "deadlines": [a for a in assignments if a["status"] != "accepted" and a["days_left"] >= 0],
            "debts": grades["debt_names"],
            "avg": grades["stats"]["avg"],
            "subjects_count": grades["stats"]["subjects"],
            "exams": exams,
            "requests": requests,
        }
        return web.json_response({"answer": ai.answer(question, ctx)})

    async def settings(request):
        u = request["user"]
        data = await body(request)
        if "notify" in data:
            await db.x("UPDATE users SET notify=? WHERE id=?", (1 if data["notify"] else 0, u["id"]))
        return web.json_response({"ok": True})

    async def index(request):
        return web.FileResponse(cfg.webapp_dir / "index.html", headers={"Cache-Control": "no-cache"})

    async def healthz(request):
        return web.Response(text="ok")

    app = web.Application(middlewares=[security_mw, auth_mw])
    r = app.router
    r.add_get("/", index)
    r.add_get("/healthz", healthz)
    r.add_post("/api/login", login)
    r.add_post("/api/logout", logout)
    r.add_get("/api/bootstrap", bootstrap)
    r.add_get("/api/schedule", schedule_week)
    r.add_post("/api/requests", create_request)
    r.add_get("/api/requests/{id}", request_detail)
    r.add_post("/api/assignments/{id}/submit", submit_assignment)
    r.add_post("/api/ai", ask_ai)
    r.add_post("/api/settings", settings)
    return app
