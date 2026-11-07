"""Запуск кабинета: HTTP-сервер + раздача веб-приложения."""
import asyncio
import logging

from aiohttp import web

from .api import build_app
from .config import load_config
from .db import DB
from .seed import seed


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    cfg = load_config()
    db = DB(cfg.db_path)
    await db.connect()
    await seed(db)

    runner = web.AppRunner(build_app(cfg, db))
    await runner.setup()
    await web.TCPSite(runner, cfg.host, cfg.port).start()
    print(f"Кабинет: http://localhost:{cfg.port}")
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
