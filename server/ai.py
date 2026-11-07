"""Ассистент по данным студента. Без внешних API: отвечает по его же расписанию и заявкам.

Так прототип не зависит от ключей и работает у жюри без настройки.
Если позже понадобится LLM — сюда добавляется серверный вызов, ключ остаётся в .env.
"""
from datetime import date

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _lessons_line(lessons: list) -> str:
    return "\n".join(f"• {l['start']} — {l['title']}, {l['room']}" for l in lessons)


def answer(question: str, ctx: dict) -> str:
    q = (question or "").lower().strip()
    if not q:
        return "Спросите что-нибудь про пары, дедлайны, оценки или заявки."

    if any(w in q for w in ("привет", "здравств", "хай")):
        return f"Привет, {ctx['first_name']}! Могу подсказать, что завтра, что сдать и как дела с учёбой."

    if any(w in q for w in ("что умеешь", "помощь", "команды")):
        return ("Я знаю ваше расписание, дедлайны, оценки и заявки. Спросите:\n"
                "• Когда следующая пара?\n• Что сдать на этой неделе?\n• Как дела с учёбой?\n"
                "• Что с моими заявками?")

    if any(w in q for w in ("завтра",)):
        tomorrow = ctx["tomorrow_lessons"]
        if not tomorrow:
            return "Завтра пар нет — можно выдохнуть."
        return f"Завтра, {ctx['tomorrow_label']}:\n{_lessons_line(tomorrow)}"

    if any(w in q for w in ("сегодня", "пары", "пара", "расписан", "занят", "когда")):
        if "следующ" in q or "ближайш" in q:
            nxt = ctx["next_lesson"]
            if not nxt:
                return "На сегодня пар больше нет."
            return (f"Следующая пара — {nxt['title']} в {nxt['start']}, "
                    f"аудитория {nxt['room']}. Начало через {nxt['in_min']} мин.")
        today = ctx["today_lessons"]
        if not today:
            return "Сегодня пар нет — свободный день."
        return f"Сегодня, {ctx['today_label']}:\n{_lessons_line(today)}"

    if any(w in q for w in ("сдать", "дедлайн", "задан", "работ", "долг")):
        parts = []
        if ctx["debts"]:
            parts.append("Долги: " + ", ".join(ctx["debts"]) + ".")
        if ctx["deadlines"]:
            parts.append("Ближайшие дедлайны:\n" + "\n".join(
                f"• {d['title']} — {d['due_label']} ({d['subject']})" for d in ctx["deadlines"][:4]))
        return "\n\n".join(parts) if parts else "Долгов и дедлайнов нет — красота."

    if any(w in q for w in ("оценк", "успева", "средн", "балл", "учёб", "учеб", "сесси")):
        text = f"Средний балл — {ctx['avg']}. Дисциплин: {ctx['subjects_count']}."
        if ctx["debts"]:
            text += "\nЕсть незакрытые: " + ", ".join(ctx["debts"]) + "."
        else:
            text += "\nДолгов нет."
        if ctx["exams"]:
            text += "\nБлижайший экзамен: " + ctx["exams"][0]
        return text

    if any(w in q for w in ("заявк", "справк", "статус", "документ")):
        if not ctx["requests"]:
            return "Заявок пока нет. Заказать справку можно в разделе «Заявки»."
        return "Ваши заявки:\n" + "\n".join(
            f"• {r['kind']} ({r['number']}) — {r['status_label']}" for r in ctx["requests"])

    return ("Не понял вопрос. Я умею про расписание, дедлайны, оценки и заявки. "
            "Например: «Что сдать на этой неделе?»")
