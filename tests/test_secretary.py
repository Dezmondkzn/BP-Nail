import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select, func

from bp_bot.domain import BusinessError
from bp_bot.models import AppValue, MeetingProtocol, ProtocolTask, User
from bp_bot.secretary import Secretary, ProtocolDraft, TaskDraft, format_protocol, protocol_schema
from test_ai_recovery import configured_ai
from test_user_management import admin_ui as admin_ui, feed


def draft(**changes):
    values = dict(
        client="ООО Заря",
        subject="Покупка бункера",
        meeting_date="2026-11-24",
        agreements="Отправить КП и уточнить доставку.",
        tasks=[
            TaskDraft(action="Отправить КП", assignee="Иван", due_date="2026-11-27", due_text="до пятницы"),
            TaskDraft(action="Уточнить доставку", due_text="после согласования"),
        ],
    )
    values.update(changes)
    return ProtocolDraft(**values).model_dump(mode="json")


def set_draft(service, uid=2, token="draft", value=None):
    with service.sessions.begin() as s:
        state = s.get(AppValue, f"conversation:{uid}")
        if state is None:
            state = AppValue(key=f"conversation:{uid}")
            s.add(state)
        state.value = {
            "mode": "secretary",
            "kind": "Звонок",
            "token": token,
            "draft": value if value is not None else draft(),
        }


@pytest.mark.parametrize("uid", [1, 2, 4])
def test_archive_survives_service_restart_and_stores_task_fields(service, uid):
    set_draft(service, uid)
    pid = Secretary(service.sessions).confirm(uid, "draft")
    archive = Secretary(service.sessions)
    assert archive.view(uid, pid)["payload"] == draft()
    assert archive.list(uid)["items"][0]["id"] == pid
    with service.sessions() as s:
        assert s.get(AppValue, f"conversation:{uid}") is None
        tasks = list(
            s.scalars(
                select(ProtocolTask).where(ProtocolTask.protocol_id == pid).order_by(ProtocolTask.position)
            )
        )
        assert tasks[0].due_date == date(2026, 11, 27)
        assert tasks[0].assignee == "Иван"
        assert tasks[1].due_date is None and tasks[1].assignee is None
        assert tasks[1].due_text == "после согласования"


def test_archive_is_private_for_every_role_and_disabled_users(service):
    set_draft(service)
    archive = Secretary(service.sessions)
    pid = archive.confirm(2, "draft")
    for uid in (1, 3, 4):
        assert archive.list(uid)["items"] == []
        with pytest.raises(BusinessError, match="не найден"):
            archive.view(uid, pid)
        with pytest.raises(BusinessError):
            archive.confirm(uid, "draft")
    with service.sessions.begin() as s:
        s.get(User, 2).active = False
    for action in (
        lambda: archive.view(2, pid),
        lambda: archive.list(2),
        lambda: archive.confirm(2, "draft"),
    ):
        with pytest.raises(BusinessError, match="Доступ закрыт"):
            action()


def test_retry_returns_same_protocol_without_deleting_next_draft(service):
    archive = Secretary(service.sessions)
    set_draft(service)
    pid = archive.confirm(2, "draft")
    set_draft(service, token="next", value=draft(client="Другой клиент"))
    assert archive.confirm(2, "draft") == pid
    with service.sessions() as s:
        assert s.get(AppValue, "conversation:2").value["token"] == "next"
        assert s.scalar(select(func.count()).select_from(MeetingProtocol)) == 1
        assert s.scalar(select(func.count()).select_from(ProtocolTask)) == 2


def test_concurrent_confirmation_creates_one_protocol(service):
    set_draft(service)
    archive = Secretary(service.sessions)
    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(lambda _: archive.confirm(2, "draft"), range(2)))
    assert ids[0] == ids[1]
    assert len(archive.list(2)["items"]) == 1


def test_stale_confirmation_and_invalid_draft_leave_archive_unchanged(service):
    archive = Secretary(service.sessions)
    set_draft(service, token="latest")
    with pytest.raises(BusinessError, match="устарела"):
        archive.confirm(2, "old")
    set_draft(service, value={"tasks": [{"action": "", "due_date": "не дата"}]})
    with pytest.raises(ValidationError):
        archive.confirm(2, "draft")
    assert archive.list(2)["items"] == []
    with service.sessions() as s:
        assert s.get(AppValue, "conversation:2") is not None


def test_legacy_draft_can_be_saved_without_inventing_tasks(service):
    text = "Клиент: Заря\nДоговорённости: Позвонить после согласования"
    set_draft(service, value=text)
    archive = Secretary(service.sessions)
    pid = archive.confirm(2, "draft")
    payload = archive.view(2, pid)["payload"]
    assert payload["tasks"] == []
    assert format_protocol(payload) == text


def test_archive_pagination(service):
    archive = Secretary(service.sessions)
    ids = []
    for i in range(11):
        set_draft(service, token=str(i))
        ids.append(archive.confirm(2, str(i)))
    first, second = archive.list(2), archive.list(2, 1)
    assert [v["id"] for v in first["items"]] == list(reversed(ids[1:]))
    assert first["has_next"] and not second["has_next"]
    assert second["items"][0]["id"] == ids[0]
    with pytest.raises(BusinessError):
        archive.list(2, -1)


def test_ai_returns_validated_structured_protocol_and_preserves_revision_input():
    result = SimpleNamespace(status="completed", output_text=json.dumps(draft()))
    ai, create = configured_ai([result])
    previous = draft(client="Другой")
    actual = asyncio.run(ai.protocol("Исправь клиента на ООО Заря", previous, date(2026, 11, 24)))
    assert actual == draft()
    assert json.loads(create.call_args.kwargs["input"])["черновик"] == previous
    schema = protocol_schema()
    assert set(schema["required"]) == set(schema["properties"])
    assert set(schema["$defs"]["TaskDraft"]["required"]) == set(schema["$defs"]["TaskDraft"]["properties"])


@pytest.mark.parametrize(
    "output",
    [
        '{"tasks":',
        '{"tasks":[{"action":"  "}]}',
        '{"tasks":[{"action":"Позвонить","due_date":"2026-02-30"}]}',
    ],
)
def test_ai_invalid_protocol_is_actionable(output):
    ai, _ = configured_ai([SimpleNamespace(status="completed", output_text=output)])
    with pytest.raises(BusinessError, match="Не удалось разобрать"):
        asyncio.run(ai.protocol("Итоги", draft(), date(2026, 11, 24)))


def test_telegram_revision_archive_navigation_and_retry(admin_ui):
    ui, bot = admin_ui
    first, revised = draft(), draft(subject="Уточнённая тема")
    ui.ai.protocol = AsyncMock(side_effect=[first, revised])

    async def flow():
        await feed(ui, bot, 2, "/secretary")
        await feed(ui, bot, 2, data=f"sec:{ui.state(2)['token']}:Встреча")
        await feed(ui, bot, 2, "Итоги встречи")
        old = ui.state(2)["token"]
        await feed(ui, bot, 2, "Исправь тему")
        token = ui.state(2)["token"]
        await feed(ui, bot, 2, data=f"sec:{old}:ok")
        assert ui.secretary.list(2)["items"] == []
        await feed(ui, bot, 2, data=f"sec:{token}:ok")
        pid = ui.secretary.list(2)["items"][0]["id"]
        assert ui.state(2) is None
        await feed(ui, bot, 2, data=f"sec:{token}:ok")
        assert len(ui.secretary.list(2)["items"]) == 1
        await feed(ui, bot, 2, "/protocols")
        assert "Уточнённая тема" in bot.session.call_args.args[1].text
        await feed(ui, bot, 2, data=f"protocol:{pid}")
        assert "Иван" in bot.session.call_args.args[1].text
        await feed(ui, bot, 2, f"/protocol {pid}")
        assert "после согласования" in bot.session.call_args.args[1].text
        await feed(ui, bot, 3, data=f"protocol:{pid}")
        assert "не найден" in bot.session.call_args.args[1].text

    asyncio.run(flow())


def test_voice_draft_is_saved_only_after_confirmation(admin_ui):
    from aiogram.types import Update

    ui, bot = admin_ui
    ui.ai.transcribe = AsyncMock(return_value="Иван отправит КП до пятницы")
    ui.ai.protocol = AsyncMock(return_value=draft())
    bot.download = AsyncMock()

    async def flow():
        await feed(ui, bot, 2, "/secretary")
        await feed(ui, bot, 2, data=f"sec:{ui.state(2)['token']}:Звонок")
        await ui.dp.feed_update(
            bot,
            Update.model_validate(
                {
                    "update_id": 901,
                    "message": {
                        "message_id": 901,
                        "date": 1793275200,
                        "chat": {"id": 2, "type": "private"},
                        "from": {"id": 2, "is_bot": False, "first_name": "Test"},
                        "voice": {
                            "file_id": "voice",
                            "file_unique_id": "unique",
                            "duration": 30,
                            "file_size": 100,
                        },
                    },
                }
            ),
        )
        assert ui.ai.protocol.call_args.args[0] == "Иван отправит КП до пятницы"
        assert ui.secretary.list(2)["items"] == []
        await feed(ui, bot, 2, data=f"sec:{ui.state(2)['token']}:ok")
        pid = ui.secretary.list(2)["items"][0]["id"]
        assert ui.secretary.view(2, pid)["payload"]["tasks"] == draft()["tasks"]

    asyncio.run(flow())


def test_failed_save_keeps_draft_and_no_partial_protocol(service):
    from sqlalchemy import event

    set_draft(service)

    def fail(*_):
        raise RuntimeError("Simulated storage failure")

    event.listen(ProtocolTask, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            Secretary(service.sessions).confirm(2, "draft")
    finally:
        event.remove(ProtocolTask, "before_insert", fail)
    assert Secretary(service.sessions).list(2)["items"] == []
    with service.sessions() as s:
        assert s.get(AppValue, "conversation:2").value["draft"] == draft()
        assert s.scalar(select(func.count()).select_from(ProtocolTask)) == 0
