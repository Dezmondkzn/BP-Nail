import asyncio
import logging
from aiogram import Bot
from sqlalchemy import text
from .ai import AI
from .bot import UI
from .config import Settings
from .models import database
from .rates import CBR
from .service import Quotes
from .storage import storage
from .jobs import Worker


async def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    settings = Settings()
    engine, sessions = database(settings.database_url)
    # Hold a session-level advisory lock for the lifetime of the polling process.
    lock_connection = None
    if engine.dialect.name == "postgresql":
        lock_connection = engine.connect()
        acquired = lock_connection.scalar(text("SELECT pg_try_advisory_lock(81426001)"))
        lock_connection.commit()
        if not acquired:
            lock_connection.close()
            engine.dispose()
            raise RuntimeError("Another bot process is already running")
    quotes = Quotes(sessions, CBR(), settings.timezone)
    await asyncio.to_thread(quotes.bootstrap, settings.bootstrap_admin_id, settings.bootstrap_admin_name)
    store, ai = storage(settings), AI(settings)
    worker = Worker(sessions, store, settings.soffice_path)
    stop = asyncio.Event()

    async def work():
        while not stop.is_set():
            try:
                await asyncio.to_thread(worker.once)
            except Exception as e:
                logging.error("worker_failure type=%s", type(e).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass

    task = asyncio.create_task(work())
    bot = Bot(settings.bot_token.get_secret_value())
    try:
        await UI(bot, quotes, ai, store, settings).run()
    finally:
        stop.set()
        await task
        await ai.close()
        await bot.session.close()
        if lock_connection is not None:
            lock_connection.close()
        engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.critical(
            "startup_failure type=%s; check configuration and service availability", type(exc).__name__
        )
        raise SystemExit(1) from None
