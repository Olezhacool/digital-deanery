import { useCallback, useEffect, useState } from "react";
import { api, type Mark, type Profile, type RequestItem, type ScheduleItem } from "./api";

const DAYS = ["", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const STATUS_LABEL: Record<string, string> = {
  new: "Новая",
  in_progress: "В работе",
  ready: "Готова",
  rejected: "Отклонена",
};

type Tab = "schedule" | "marks" | "requests";

function App() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("schedule");

  useEffect(() => {
    const tg = (window as unknown as { Telegram?: { WebApp?: { ready?: () => void; expand?: () => void } } }).Telegram;
    tg?.WebApp?.ready?.();
    tg?.WebApp?.expand?.();
  }, []);

  useEffect(() => {
    api
      .me()
      .then(setProfile)
      .catch(() => setError("Не удалось войти. Откройте приложение из Telegram."));
  }, []);

  if (error) return <div className="screen"><div className="card muted">{error}</div></div>;
  if (!profile) return <div className="screen"><div className="card muted">Загружаю кабинет…</div></div>;

  return (
    <div className="screen">
      <header className="card profile">
        <div className="profile-avatar">{profile.full_name.slice(0, 1)}</div>
        <div>
          <div className="profile-name">{profile.full_name}</div>
          <div className="muted">{profile.group_title ?? "—"} · {profile.course} курс</div>
          <div className="muted small">{profile.faculty}</div>
        </div>
        {profile.role !== "student" && <span className="badge role">{profile.role === "owner" ? "Владелец" : "Сотрудник"}</span>}
      </header>

      <nav className="tabs">
        {(["schedule", "marks", "requests"] as Tab[]).map((t) => (
          <button key={t} className={"tab" + (tab === t ? " active" : "")} onClick={() => setTab(t)}>
            {t === "schedule" ? "Расписание" : t === "marks" ? "Оценки" : "Заявки"}
          </button>
        ))}
      </nav>

      {tab === "schedule" && <Schedule />}
      {tab === "marks" && <Marks />}
      {tab === "requests" && <Requests role={profile.role} />}
    </div>
  );
}

function Schedule() {
  const [items, setItems] = useState<ScheduleItem[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.schedule().then(setItems).catch(() => setErr("Не удалось загрузить расписание"));
  }, []);
  if (err) return <div className="card muted">{err}</div>;
  if (!items) return <div className="card muted">Загружаю…</div>;
  if (!items.length) return <div className="card">Пока нет пар — отличный день, чтобы закрыть хвосты.</div>;
  return (
    <div className="card">
      {items.map((s, i) => (
        <div key={i} className="row">
          <div className="row-time">{DAYS[s.day]} · {s.start}</div>
          <div className="row-main">{s.discipline}<div className="muted small">{s.kind} · {s.room}</div></div>
        </div>
      ))}
    </div>
  );
}

function Marks() {
  const [marks, setMarks] = useState<Mark[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.marks().then(setMarks).catch(() => setErr("Не удалось загрузить оценки"));
  }, []);
  if (err) return <div className="card muted">{err}</div>;
  if (!marks) return <div className="card muted">Загружаю…</div>;
  if (!marks.length) return <div className="card">Оценок пока нет.</div>;
  return (
    <div className="card">
      {marks.map((m) => (
        <div key={m.id} className="row">
          <div className="row-main">{m.discipline}<div className="muted small">{m.teacher} · {m.kind}</div></div>
          <div className={"mark " + (m.value === "незачёт" ? "mark-bad" : "mark-good")}>{m.value}</div>
        </div>
      ))}
    </div>
  );
}

function Requests({ role }: { role: Profile["role"] }) {
  const [data, setData] = useState<{ all: boolean; items: RequestItem[] } | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.requests().then(setData).catch(() => setErr("Не удалось загрузить заявки"));
  }, []);

  useEffect(load, [load]);

  const create = async () => {
    setBusy(true);
    try {
      await api.createRequest("certificate");
      load();
    } finally {
      setBusy(false);
    }
  };

  if (err) return <div className="card muted">{err}</div>;
  if (!data) return <div className="card muted">Загружаю…</div>;

  return (
    <div className="stack">
      <div className="card">
        {data.items.length === 0 ? (
          <div>Пока нет заявок — создайте первую.</div>
        ) : (
          data.items.map((r) => (
            <div key={r.id} className="row">
              <div className="row-main">
                {r.type_label}
                <div className="muted small">от {r.created_at.slice(0, 10)}</div>
              </div>
              <span className={"badge st-" + r.status}>{STATUS_LABEL[r.status] ?? r.status}</span>
            </div>
          ))
        )}
      </div>
      {role === "student" ? (
        <button className="btn" onClick={create} disabled={busy}>
          {busy ? "Отправляю…" : "Заказать справку об обучении"}
        </button>
      ) : (
        <div className="muted small center">Вы видите заявки всех студентов ({data.items.length}).</div>
      )}
    </div>
  );
}

export default App;
