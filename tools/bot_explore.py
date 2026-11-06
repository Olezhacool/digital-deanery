#!/usr/bin/env python3
"""bot_explore.py - проходит Telegram-бота как живой пользователь и сохраняет всё,
что бот показывает: тексты, кнопки, callback-данные, ссылки на мини-апп.

Зачем: изучить чужого бота без скриншотов.

Установка и запуск (PowerShell):

    pip install telethon
    python tools/bot_explore.py @username_бота

Первый запуск спросит телефон и код из Telegram - вводишь сам в своём терминале.
Сессия остаётся локально в tools/.tg-session (в git не попадает).

Результат: research/bot-<имя>-<дата>.json и research/bot-<имя>-<дата>.md

Флаги:
    --depth 2         на сколько уровней вглубь жать кнопки (по умолчанию 2)
    --max-clicks 30   предохранитель: сколько нажатий максимум (по умолчанию 30)
    --wait 1.6        пауза после нажатия, сек (по умолчанию 1.6)
    --dry             только /start и меню-кнопка, кнопки не жать

Осторожно: это чужой бот. Нажатия могут создавать записи на его сервере.
"""

import argparse
import asyncio
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from telethon import TelegramClient, errors
except ImportError:
    sys.exit("Нет telethon. Установи:  pip install telethon")

# Кнопка меню и описание бота: именно там обычно лежит ссылка на мини-апп.
try:
    from telethon.tl.functions.bots import GetBotMenuButtonRequest, GetBotInfoRequest
except ImportError:
    GetBotMenuButtonRequest = GetBotInfoRequest = None

# Публичная пара Telegram Desktop - по ней логинится любой клиент.
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
OUT_DIR = ROOT / "research"
SESSION = TOOLS / ".tg-session"


def b64(data):
    return base64.b64encode(data).decode() if data else None


def buttons_of(msg):
    """Кнопки: inline (есть data), web_app (есть url), reply (нижняя клавиатура)."""
    out = []
    for row in (msg.buttons or []):
        for btn in row:
            data = getattr(btn, "data", None)
            inner = getattr(btn, "button", None)
            url = getattr(btn, "url", None) or getattr(inner, "url", None)
            out.append({
                "text": btn.text,
                "data_b64": b64(data),
                "url": url,
                "kind": type(inner).__name__ if inner else None,
                "inline": data is not None,
            })
    return out


def node(msg, depth, action, target=None):
    return {
        "depth": depth,
        "action": action,
        "target": target,
        "msg_id": msg.id,
        "date": msg.date.isoformat() if msg.date else None,
        "text": msg.text or "",
        "buttons": buttons_of(msg),
        "has_media": bool(msg.media),
    }


async def drain(client, bot, last_id, wait):
    """Забрать всё, что бот прислал после last_id."""
    await asyncio.sleep(wait)
    try:
        msgs = await client.get_messages(bot, min_id=last_id, limit=40)
    except errors.FloodWaitError as e:
        print("  flood wait %ss, жду..." % e.seconds)
        await asyncio.sleep(e.seconds + 2)
        msgs = await client.get_messages(bot, min_id=last_id, limit=40)
    return sorted(msgs, key=lambda m: m.id)


async def read_menu(client, bot):
    """Кнопка меню бота - самый вероятный носитель ссылки на мини-апп."""
    if not GetBotMenuButtonRequest:
        return {"error": "нет GetBotMenuButtonRequest в этой версии telethon"}
    try:
        mb = await client(GetBotMenuButtonRequest(bot=bot))
    except Exception as e:
        return {"error": str(e)}
    menu = {"type": type(mb).__name__}
    for attr in ("url", "text"):
        val = getattr(mb, attr, None)
        if val:
            menu[attr] = val
    return menu


async def read_info(client, bot):
    """Описание и команды бота - из них видно, что он умеет."""
    if not GetBotInfoRequest:
        return {}
    try:
        bi = await client(GetBotInfoRequest(bot=bot, lang_code="ru"))
    except Exception as e:
        return {"error": str(e)}
    return {
        "description": getattr(bi, "description", None),
        "commands": [
            {"command": c.command, "description": c.description}
            for c in (getattr(bi, "commands", None) or [])
        ],
    }


async def main():
    ap = argparse.ArgumentParser(description="Обход Telegram-бота и запись его структуры")
    ap.add_argument("target", help="@username бота")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--max-clicks", type=int, default=30)
    ap.add_argument("--wait", type=float, default=1.6)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)

    client = TelegramClient(str(SESSION), API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print("вошёл как %s (@%s)" % (me.first_name, me.username))

    bot = await client.get_entity(args.target)
    print("бот: %s @%s  id=%s" % (bot.first_name, bot.username, bot.id))

    menu = await read_menu(client, bot)
    if menu.get("url"):
        print("мини-апп (кнопка меню): %s" % menu["url"])
    elif menu.get("error"):
        print("кнопка меню: %s" % menu["error"])

    info = await read_info(client, bot)
    if info.get("description"):
        print("описание: %s" % info["description"].replace("\n", " ")[:200])
    if info.get("commands"):
        print("команды: %s" % ", ".join("/" + c["command"] for c in info["commands"]))

    nodes = []
    queue = [(None, None, None, 0)]     # (msg_id, data_b64, label, depth)
    seen = set()
    clicks = 0

    hist = await client.get_messages(bot, limit=1)
    last_id = hist[0].id if hist else 0

    while queue:
        msg_id, data_b64, label, depth = queue.pop(0)

        if msg_id is None:
            print("-> /start")
            await client.send_message(bot, "/start")
            action, target = "/start", None
        else:
            if clicks >= args.max_clicks:
                print("достигнут --max-clicks %s, останавливаюсь" % args.max_clicks)
                break
            raw = base64.b64decode(data_b64) if data_b64 else None
            if raw is None:
                continue
            try:
                m = await client.get_messages(bot, ids=msg_id)
                await m.click(data=raw)
                clicks += 1
                action, target = "click", label or data_b64
                print("%s-> «%s» (глубина %s)" % ("  " * depth, label or "callback", depth))
            except errors.FloodWaitError as e:
                print("  flood wait %ss, жду..." % e.seconds)
                await asyncio.sleep(e.seconds + 2)
                continue
            except Exception as e:
                print("  кнопка не нажалась: %s" % e)
                nodes.append({"depth": depth, "action": "click_failed",
                              "target": label or data_b64, "error": str(e)})
                continue

        produced = await drain(client, bot, last_id, args.wait)
        for pm in produced:
            last_id = max(last_id, pm.id)
            nodes.append(node(pm, depth, action, target))
            if args.dry or depth + 1 >= args.depth:
                continue
            for b in buttons_of(pm):
                if b["inline"] and (pm.id, b["data_b64"]) not in seen:
                    seen.add((pm.id, b["data_b64"]))
                    queue.append((pm.id, b["data_b64"], b["text"], depth + 1))

        if not produced:
            print("%s(бот молчит)" % ("  " * depth))

    await client.disconnect()

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    name = (bot.username or str(bot.id)).replace("/", "_")
    stem = "bot-%s-%s" % (name, stamp)

    payload = {
        "bot": {"id": bot.id, "username": bot.username, "name": bot.first_name},
        "explored_at": datetime.now(timezone.utc).isoformat(),
        "params": {"depth": args.depth, "max_clicks": args.max_clicks, "dry": args.dry},
        "menu_button": menu,
        "bot_info": info,
        "clicks": clicks,
        "nodes": nodes,
    }
    (OUT_DIR / (stem + ".json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# Разбор бота @%s" % bot.username, "",
             "Снято: %s · состояний: %s · нажатий: %s" % (payload["explored_at"], len(nodes), clicks)]
    if menu.get("url"):
        lines.append("")
        lines.append("**Мини-апп:** %s" % menu["url"])
    if info.get("description"):
        lines.append("")
        lines.append("**Описание:** %s" % info["description"])
    if info.get("commands"):
        lines.append("")
        lines.append("**Команды:** %s" % ", ".join("/" + c["command"] for c in info["commands"]))
    lines += ["", "---", ""]

    for n in nodes:
        if n.get("action") == "click_failed":
            lines.append("%s~~кнопка не нажалась: %s~~" % ("  " * n["depth"], n.get("error")))
            lines.append("")
            continue
        head = "  " * n["depth"]
        lines.append("%s### [%s]" % (head, n["action"]))
        if n["text"]:
            lines.append("")
            for ln in n["text"].split("\n"):
                lines.append(head + ln)
        if n["buttons"]:
            lines.append("")
            for b in n["buttons"]:
                kind = "inline" if b["inline"] else ("url" if b["url"] else "reply")
                extra = (" -> " + b["url"]) if b["url"] else ""
                lines.append("%s- `[%s]` (%s)%s" % (head, b["text"], kind, extra))
        lines.append("")

    (OUT_DIR / (stem + ".md")).write_text("\n".join(lines), encoding="utf-8")

    print()
    print("готово: %s состояний, %s нажатий" % (len(nodes), clicks))
    print("  %s" % (OUT_DIR / (stem + ".json")))
    print("  %s" % (OUT_DIR / (stem + ".md")))
    if menu.get("url"):
        print()
        print("МИНИ-АПП: %s" % menu["url"])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit("прервано")
