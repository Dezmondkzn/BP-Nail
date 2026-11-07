import asyncio
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy import select

from bp_bot.ai import AI
from bp_bot.bot import UI
from bp_bot.config import Settings
from bp_bot.jobs import Worker
from bp_bot.models import Job
from bp_bot.storage import LocalStorage
from test_quotes import patch


def setup_ui(service, tmp_path):
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    store = LocalStorage(tmp_path)
    store.put("letterheads/test.docx", b"letterhead", "application/octet-stream")
    ui = UI(bot, service, AI(settings), store, settings)
    message = Message.model_validate(
        {"message_id": 900, "date": 1793275200, "chat": {"id": 2, "type": "private"}}
    ).as_(bot)
    qid = service.create(2, patch(), "delivery-test")["id"]
    service.finish(2, qid, 1)
    worker = Worker(service.sessions, store, renderer=lambda *_: (b"docx", b"%PDF-1.7"))
    return ui, bot, store, message, qid, worker


def test_queued_documents_arrive_without_second_click_and_are_deduplicated(service, tmp_path):
    ui, bot, _, message, qid, worker = setup_ui(service, tmp_path)

    async def flow():
        await ui.files(message, qid, 1)
        sent = bot.session.call_args.args[1]
        assert (
            sent.text
            == "Документы в очереди. Через несколько секунд они выгрузятся сюда в формате «Word и PDF»"
        )
        assert sent.reply_markup is None
        await ui.files(message, qid, 1)
        assert len(service.pending_file_deliveries()) == 1
        await ui.deliver_pending_files()
        assert not any(type(call.args[1]).__name__ == "SendDocument" for call in bot.session.call_args_list)
        assert worker.once()
        await ui.deliver_pending_files()
        await ui.deliver_pending_files()
        docs = [
            call.args[1]
            for call in bot.session.call_args_list
            if type(call.args[1]).__name__ == "SendDocument"
        ]
        assert [d.document.filename for d in docs] == [f"KP-{qid:05d}_v1.docx", f"KP-{qid:05d}_v1.pdf"]
        assert all(d.chat_id == 2 for d in docs)
        assert service.pending_file_deliveries() == []

    asyncio.run(flow())


def test_delivery_survives_restart_and_retries_only_unsent_file(service, tmp_path):
    ui, bot, store, message, qid, worker = setup_ui(service, tmp_path)

    async def flow():
        await ui.files(message, qid, 1)
        assert worker.once()
        original = bot.send_document
        calls = []

        async def send(uid, document):
            calls.append(document.filename)
            if document.filename.endswith("pdf"):
                raise OSError("temporary transport failure")
            return await original(uid, document)

        bot.send_document = send
        await ui.deliver_pending_files()
        assert service.pending_file_deliveries()[0]["sent"] == ["docx"]
        bot.send_document = original
        restarted = UI(bot, service, ui.ai, store, ui.settings)
        await restarted.deliver_pending_files()
        docs = [
            call.args[1]
            for call in bot.session.call_args_list
            if type(call.args[1]).__name__ == "SendDocument"
        ]
        assert [d.document.filename for d in docs] == [f"KP-{qid:05d}_v1.docx", f"KP-{qid:05d}_v1.pdf"]
        assert len(calls) == 2
        assert service.pending_file_deliveries() == []

    asyncio.run(flow())


def test_revoked_user_does_not_receive_queued_documents(service, tmp_path):
    ui, bot, _, message, qid, worker = setup_ui(service, tmp_path)

    async def flow():
        await ui.files(message, qid, 1)
        worker.once()
        service.set_user(1, 2, "manager", "main", "Менеджер", False)
        bot.session.reset_mock()
        await ui.deliver_pending_files()
        bot.session.assert_not_called()
        assert service.pending_file_deliveries() == []

    asyncio.run(flow())


def test_permanent_generation_failure_notifies_once_without_automatic_retry(service, tmp_path):
    ui, bot, _, message, qid, _ = setup_ui(service, tmp_path)

    async def flow():
        await ui.files(message, qid, 1)
        with service.sessions.begin() as s:
            job = s.scalar(select(Job))
            job.state, job.attempts = "failed", 3
        bot.session.reset_mock()
        await ui.deliver_pending_files()
        await ui.deliver_pending_files()
        assert bot.session.call_count == 1
        assert "Не удалось подготовить" in bot.session.call_args.args[1].text
        with service.sessions() as s:
            assert s.scalar(select(Job)).state == "failed"
        assert service.pending_file_deliveries() == []

    asyncio.run(flow())
