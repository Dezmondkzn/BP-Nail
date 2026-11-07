import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from bp_bot.ai import AI
from bp_bot.config import Settings
from bp_bot.domain import BusinessError, ProposalPatch


def invalid_response():
    try:
        ProposalPatch.model_validate_json('{"client":"PRIVATE CUSTOMER",')
    except ValidationError as error:
        return error


def configured_ai(results):
    settings = Settings(
        bot_token="123456:TEST",
        database_url="sqlite://",
        app_env="development",
        storage_backend="local",
        openai_text_model="test-model",
    )
    ai = AI(settings)
    parse = AsyncMock(side_effect=results)
    ai.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    return ai, parse


def response(patch=None, status="completed", reason=None):
    return SimpleNamespace(
        status=status,
        output_parsed=patch,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
    )


@pytest.mark.parametrize(
    "first", [invalid_response(), response(status="incomplete", reason="max_output_tokens")]
)
def test_invalid_or_truncated_ai_response_recovers(first, caplog):
    patch = ProposalPatch(client="Заря")
    ai, parse = configured_ai([first, response(patch)])
    assert asyncio.run(ai.parse("Сделай КП для Зари", date(2026, 11, 7))) == patch
    assert parse.await_count == 2
    assert (
        parse.call_args_list[1].kwargs["max_output_tokens"]
        > parse.call_args_list[0].kwargs["max_output_tokens"]
    )
    assert parse.call_args_list[1].kwargs["input"] == parse.call_args_list[0].kwargs["input"]
    assert "PRIVATE CUSTOMER" not in caplog.text


def test_repeated_invalid_response_is_bounded_and_actionable(caplog):
    ai, parse = configured_ai([invalid_response(), invalid_response()])
    with pytest.raises(BusinessError, match="пришлите исправленный запрос текстом"):
        asyncio.run(ai.parse("Сделай КП", date(2026, 11, 7)))
    assert parse.await_count == 2
    assert "PRIVATE CUSTOMER" not in caplog.text


def test_retry_does_not_bypass_business_rules():
    ai, _ = configured_ai([invalid_response(), response(ProposalPatch(forbidden_requests=["Изменить НДС"]))])
    with pytest.raises(BusinessError, match="Нельзя менять"):
        asyncio.run(ai.parse("Измени НДС", date(2026, 11, 7)))


def test_refusal_is_not_retried():
    ai, parse = configured_ai([response()])
    with pytest.raises(BusinessError):
        asyncio.run(ai.parse("Сделай КП", date(2026, 11, 7)))
    assert parse.await_count == 1
