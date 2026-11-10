import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Update

from bp_bot.domain import BusinessError
from bp_bot.models import User, Quote
import test_user_management as management
from test_quotes import patch

feed = management.feed


@pytest.fixture
def admin_ui(service, tmp_path):
    return management.admin_ui.__wrapped__(service, tmp_path)




async def start_with_nick(ui, bot, uid, username):
    await ui.dp.feed_update(
        bot,
        Update.model_validate(
            {
                "update_id": 1000,
                "message": {
                    "message_id": 1000,
                    "date": 1793275200,
                    "chat": {"id": uid, "type": "private"},
                    "from": {
                        "id": uid,
                        "is_bot": False,
                        "first_name": "Новый",
                        "last_name": "Менеджер",
                        "username": username,
                    },
                    "text": "/start",
                },
            }
        ),
    )


def test_start_remembers_username_without_granting_access(admin_ui, service):
    ui, bot = admin_ui
    asyncio.run(start_with_nick(ui, bot, 555, "New_Manager"))
    assert service.resolve_user_reference(1, "@NEW_MANAGER")["id"] == 555
    assert "@New_Manager" in bot.session.call_args.args[1].text
    with pytest.raises(BusinessError):
        service.user(555)
    with pytest.raises(BusinessError):
        service.resolve_user_reference(2, "@NEW_MANAGER")


def test_add_by_username_uses_observed_id_and_role_selection(admin_ui, service):
    ui, bot = admin_ui
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username="New_Manager"))

    async def flow():
        await start_with_nick(ui, bot, 555, "New_Manager")
        await feed(ui, bot, 1, "/adduser @NEW_MANAGER")
        state = ui.state(1)
        assert state["mode"] == "add_user_role"
        assert state["id"] == 555
        await feed(ui, bot, 1, data=f"user_role:{state['token']}:manager")
        assert service.user(555).role == "manager"
        assert service.user(555).name == "Новый Менеджер"
        assert ui.state(1) is None

    asyncio.run(flow())


def test_unknown_username_requires_start(admin_ui, service):
    ui, bot = admin_ui
    asyncio.run(feed(ui, bot, 1, "/adduser @unknown_name"))
    assert "отправить боту /start" in bot.session.call_args.args[1].text
    assert len(service.users(1)) == 4


def test_changed_or_recycled_username_never_moves_access(service):
    service.remember_telegram_identity(2, "old_manager", "Менеджер")
    service.remember_telegram_identity(2, "new_manager", "Менеджер")
    with pytest.raises(BusinessError):
        service.resolve_user_reference(1, "@old_manager")
    service.remember_telegram_identity(999, "new_manager", "Другой человек")
    assert service.resolve_user_reference(1, "@new_manager")["id"] == 999
    assert service.user(2).role == "manager"
    with pytest.raises(BusinessError):
        service.user(999)
    with pytest.raises(BusinessError, match="Ник изменился"):
        service.set_user(1, 2, "chief", "main", "Wrong", expected_username="new_manager")
    assert service.user(2).role == "manager"
    service.remember_telegram_identity(999, None, "Другой человек")
    with pytest.raises(BusinessError):
        service.resolve_user_reference(1, "@new_manager")


def test_role_button_rejects_recycled_username(admin_ui, service):
    ui, bot = admin_ui
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username="new_manager"))

    async def flow():
        await start_with_nick(ui, bot, 555, "new_manager")
        await feed(ui, bot, 1, "/adduser @new_manager")
        token = ui.state(1)["token"]
        service.remember_telegram_identity(777, "new_manager", "Новый владелец ника")
        await feed(ui, bot, 1, data=f"user_role:{token}:chief")
        assert "Ник изменился" in bot.session.call_args.args[1].text
        for uid in (555, 777):
            with pytest.raises(BusinessError):
                service.user(uid)

    asyncio.run(flow())


def test_live_username_check_rejects_stale_identity(admin_ui, service):
    ui, bot = admin_ui
    service.remember_telegram_identity(555, "old_manager", "Менеджер")
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username="new_manager"))
    asyncio.run(feed(ui, bot, 1, "/adduser @old_manager"))
    assert "сменил ник" in bot.session.call_args.args[1].text
    with pytest.raises(BusinessError):
        service.resolve_user_reference(1, "@old_manager")


def test_disable_by_username_keeps_quotes_and_start_does_not_restore_access(admin_ui, service):
    ui, bot = admin_ui
    bot.get_chat = AsyncMock(return_value=SimpleNamespace(username="manager_two"))
    service.remember_telegram_identity(2, "manager_two", "Менеджер")
    qid = service.create(2, patch(), "keep-history")["id"]

    async def flow():
        await feed(ui, bot, 1, "/disable @MANAGER_TWO")
        assert "КП и история сохранены" in bot.session.call_args.args[1].text
        with service.sessions() as s:
            assert not s.get(User, 2).active
            assert s.get(Quote, qid) is not None
        await start_with_nick(ui, bot, 2, "manager_two")
        with pytest.raises(BusinessError):
            service.user(2)
        assert service.view(1, qid)["payload"]["client"]

    asyncio.run(flow())


def test_disable_wizard_is_chief_only_and_rejects_self(admin_ui, service):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, 2, "/disable 3")
        assert service.user(3).active
        await feed(ui, bot, 1, "/disable")
        assert ui.state(1)["mode"] == "disable_user"
        await feed(ui, bot, 1, "1")
        assert service.user(1).active
        assert "самого себя" in bot.session.call_args.args[1].text
        await feed(ui, bot, 1, "3")
        assert ui.state(1) is None
        with pytest.raises(BusinessError):
            service.user(3)

    asyncio.run(flow())
