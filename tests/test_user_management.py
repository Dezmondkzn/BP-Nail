import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Update

from bp_bot.ai import AI
from bp_bot.bot import UI
from bp_bot.config import Settings
from bp_bot.domain import BusinessError
from bp_bot.storage import LocalStorage


@pytest.fixture
def admin_ui(service, tmp_path):
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    return UI(bot, service, AI(settings), LocalStorage(tmp_path), settings), bot


async def feed(ui, bot, uid, text=None, data=None):
    message = {"message_id": 900, "date": 1793275200, "chat": {"id": uid, "type": "private"}}
    actor = {"id": uid, "is_bot": False, "first_name": "Test"}
    if data is None:
        update = {"message": {**message, "from": actor, "text": text}}
    else:
        update = {
            "callback_query": {
                "id": "900",
                "chat_instance": "test",
                "from": actor,
                "data": data,
                "message": {
                    **message,
                    "text": "Выберите роль",
                    "from": {"id": 123456, "is_bot": True, "first_name": "Bot"},
                },
            }
        }
    await ui.dp.feed_update(bot, Update.model_validate({"update_id": 900, **update}))


@pytest.mark.parametrize("role", ["manager", "sales_head", "chief"])
def test_chief_adds_user_with_selected_role(admin_ui, service, role):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, 1, "/adduser")
        await feed(ui, bot, 1, "123456789")
        await feed(ui, bot, 1, "Иван Иванов")
        state = ui.state(1)
        assert state["mode"] == "add_user_role"
        data = f"user_role:{state['token']}:{role}"
        await feed(ui, bot, 1, data=data)
        user = service.user(123456789)
        assert (user.name, user.role, user.department, user.active) == ("Иван Иванов", role, "main", True)
        assert ui.state(1) is None
        assert "Пользователь добавлен" in bot.session.call_args.args[1].text
        await feed(ui, bot, 1, data=data)
        assert "уже завершено" in bot.session.call_args.args[1].text
        assert service.user(123456789).role == role

    asyncio.run(flow())


@pytest.mark.parametrize("actor", [2, 4])
def test_non_chief_cannot_create_users_even_with_forged_callback(admin_ui, service, actor):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, actor, "/adduser")
        assert ui.state(actor) is None
        await feed(ui, bot, actor, data="users:add")
        assert ui.state(actor) is None
        ui.state(actor, {"mode": "add_user_role", "token": "forged", "id": 999, "name": "Test"})
        await feed(ui, bot, actor, data="user_role:forged:chief")
        assert "только начальнику" in bot.session.call_args.args[1].text
        with pytest.raises(BusinessError):
            service.user(999)

    asyncio.run(flow())


def test_invalid_id_duplicate_and_cancel_keep_user_data_intact(admin_ui, service):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, 1, "/adduser")
        for value in ("@username", "0", "-5", str(2**63), "9" * 5000):
            await feed(ui, bot, 1, value)
            assert ui.state(1)["mode"] == "add_user_id"
        await feed(ui, bot, 1, "2")
        assert "уже добавлен" in bot.session.call_args.args[1].text
        assert service.user(2).role == "manager"
        await feed(ui, bot, 1, "555")
        await feed(ui, bot, 1, "Новый пользователь")
        token = ui.state(1)["token"]
        await feed(ui, bot, 1, "/cancel")
        await feed(ui, bot, 1, data=f"user_role:{token}:chief")
        with pytest.raises(BusinessError):
            service.user(555)

    asyncio.run(flow())


def test_existing_user_cannot_be_overwritten_between_steps(admin_ui, service):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, 1, "/users")
        assert bot.session.call_args.args[1].reply_markup.inline_keyboard[0][0].callback_data == "users:add"
        await feed(ui, bot, 1, data="users:add")
        await feed(ui, bot, 1, "555")
        await feed(ui, bot, 1, "Новый пользователь")
        token = ui.state(1)["token"]
        service.set_user(1, 555, "manager", "other", "Уже добавлен", False)
        await feed(ui, bot, 1, data=f"user_role:{token}:chief")
        assert "уже добавлен" in bot.session.call_args.args[1].text
        user = next(u for u in service.users(1) if u.telegram_id == 555)
        assert (user.role, user.department, user.active) == ("manager", "other", False)

    asyncio.run(flow())


def test_role_is_rechecked_on_every_wizard_step(admin_ui, service):
    ui, bot = admin_ui

    async def flow():
        service.set_user(1, 50, "chief", "main", "Второй начальник")
        await feed(ui, bot, 50, "/adduser")
        await feed(ui, bot, 50, "555")
        service.set_user(1, 50, "manager", "main", "Бывший начальник")
        await feed(ui, bot, 50, "Новый пользователь")
        assert "только начальнику" in bot.session.call_args.args[1].text
        with pytest.raises(BusinessError):
            service.user(555)

    asyncio.run(flow())


def menus(bot):
    return [
        call.args[1] for call in bot.session.call_args_list if type(call.args[1]).__name__ == "SetMyCommands"
    ]


def test_start_and_role_changes_refresh_chat_command_menu(admin_ui, service):
    ui, bot = admin_ui

    async def flow():
        await feed(ui, bot, 1, "/start")
        chief_menu = menus(bot)[-1]
        assert chief_menu.scope.chat_id == 1
        assert {"adduser", "users", "new"} <= {c.command for c in chief_menu.commands}
        await feed(ui, bot, 2, "/start")
        assert "adduser" not in {c.command for c in menus(bot)[-1].commands}
        await feed(ui, bot, 1, "/user 2 chief main Менеджер")
        assert menus(bot)[-1].scope.chat_id == 2
        assert "adduser" in {c.command for c in menus(bot)[-1].commands}
        await feed(ui, bot, 1, "/user 2 manager main Менеджер")
        assert "adduser" not in {c.command for c in menus(bot)[-1].commands}

    asyncio.run(flow())


def test_startup_refreshes_chief_menu_and_clears_disabled_chief_menu(admin_ui, service):
    from types import SimpleNamespace

    ui, bot = admin_ui
    service.set_user(1, 50, "chief", "main", "Отключённый начальник", False)
    bot.get_webhook_info = AsyncMock(return_value=SimpleNamespace(url=""))
    ui.dp.start_polling = AsyncMock()
    asyncio.run(ui.run())
    scoped = {m.scope.chat_id: {c.command for c in m.commands} for m in menus(bot) if m.scope is not None}
    assert "adduser" in scoped[1]
    assert "adduser" not in scoped[2]
    assert "adduser" not in scoped[50]
    ui.dp.start_polling.assert_awaited_once()


def test_unknown_chat_menu_failure_does_not_block_user_creation(admin_ui, service):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SetMyCommands

    ui, bot = admin_ui
    bot.set_my_commands = AsyncMock(
        side_effect=TelegramBadRequest(method=SetMyCommands(commands=[]), message="chat not found")
    )

    async def flow():
        await feed(ui, bot, 1, "/adduser")
        await feed(ui, bot, 1, "555")
        await feed(ui, bot, 1, "Новый пользователь")
        await feed(ui, bot, 1, data=f"user_role:{ui.state(1)['token']}:chief")
        assert service.user(555).role == "chief"
        assert "Пользователь добавлен" in bot.session.call_args.args[1].text

    asyncio.run(flow())
