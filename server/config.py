"""Настройки из переменных окружения."""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    db_path: str
    secret: str
    tz: ZoneInfo
    semester_start: date
    cookie_secure: bool
    webapp_dir: Path


def load_config() -> Config:
    secret = os.getenv("SECRET", "").strip()
    if not secret or secret == "change-me-to-a-long-random-string":
        raise SystemExit("SECRET не задан. Скопируйте .env.example в .env и укажите случайную строку.")

    db_path = os.getenv("DB_PATH", "storage/deanery.db")
    if not os.path.isabs(db_path):
        db_path = str(ROOT / db_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return Config(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
        db_path=db_path,
        secret=secret,
        tz=ZoneInfo(os.getenv("TZ_NAME", "Europe/Moscow")),
        semester_start=date.fromisoformat(os.getenv("SEMESTER_START", "2026-08-31")),
        cookie_secure=os.getenv("COOKIE_SECURE", "0") == "1",
        webapp_dir=ROOT / "webapp",
    )
