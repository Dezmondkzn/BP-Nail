import asyncio
from unittest.mock import AsyncMock
from aiogram import Bot
from aiogram.types import Update
from bp_bot.bot import UI
from bp_bot.ai import AI
from bp_bot.config import Settings
from bp_bot.storage import LocalStorage
from bp_bot.models import RequestReceipt


def test_telegram_text_flow_and_forbidden_user(service, tmp_path):
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    ui = UI(bot, service, AI(settings), LocalStorage(tmp_path), settings)

    async def send(uid, mid, text):
        update = Update.model_validate(
            {
                "update_id": mid,
                "message": {
                    "message_id": mid,
                    "date": 1793275200,
                    "chat": {"id": uid, "type": "private"},
                    "from": {"id": uid, "is_bot": False, "first_name": "Test"},
                    "text": text,
                },
            }
        )
        await ui.dp.feed_update(bot, update)

    async def flow():
        await send(2, 100, "/new клиент=ООО A&B; позиции=A:1; поставка=10 дней; до=2026-11-05")
        q = service.list_quotes(2)[0]["id"]
        await send(2, 101, f"/finish {q} 1")
        assert service.view(2, q)["status"] == "finished"
        await send(3, 102, f"/show {q}")
        assert "Нет доступа" in bot.session.call_args.args[1].text
        await send(2, 103, f"/vat {q} 1 10 Причина")
        assert service.view(2, q)["version"] == 1
        await send(2, 104, f"/edit {q} 1 клиент=Другой")
        assert service.view(2, q)["version"] == 2
        with service.sessions() as s:
            assert s.get(RequestReceipt, "message:2:104") is not None

    asyncio.run(flow())
