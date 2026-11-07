import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bp_bot.ai import AI
from bp_bot.config import Settings
from bp_bot.domain import BusinessError, ProposalPatch


def invalid_response():
    return response(raw='{"client":"PRIVATE CUSTOMER",')


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
    ai.client = SimpleNamespace(responses=SimpleNamespace(create=parse))
    return ai, parse


def response(patch=None, status="completed", reason=None, raw=None):
    content = (
        [SimpleNamespace(type="output_text", text=raw if raw is not None else patch.model_dump_json())]
        if raw is not None or patch is not None
        else [SimpleNamespace(type="refusal")]
    )
    return SimpleNamespace(
        status=status,
        output=[SimpleNamespace(type="message", content=content, phase=None)],
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


def test_final_json_ignores_non_json_commentary():
    result = response(ProposalPatch(client="Заря"))
    result.output[0].phase = "final_answer"
    result.output.insert(
        0,
        SimpleNamespace(
            type="message",
            phase="commentary",
            content=[SimpleNamespace(type="output_text", text="Подготовлю коммерческое предложение.")],
        ),
    )
    ai, create = configured_ai([result])
    assert asyncio.run(ai.parse("КП для Зари", date(2026, 11, 7))).client == "Заря"
    assert create.await_count == 1


def test_real_sdk_incomplete_json_is_checked_before_validation(caplog):
    import json
    import httpx
    from openai import AsyncOpenAI

    requests = []

    def serve(request):
        requests.append(json.loads(request.content))
        incomplete = len(requests) == 1
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1794038400,
                "model": "test-model",
                "status": "incomplete" if incomplete else "completed",
                "incomplete_details": {"reason": "max_output_tokens"} if incomplete else None,
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "incomplete" if incomplete else "completed",
                        "phase": "final_answer",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": '{"client":"PRIVATE CUSTOMER",'
                                if incomplete
                                else ProposalPatch(client="Заря").model_dump_json(),
                            }
                        ],
                    }
                ],
            },
        )

    async def flow():
        ai, _ = configured_ai([])
        async with AsyncOpenAI(
            api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(serve))
        ) as client:
            ai.client = client
            return await ai.parse("КП для Зари", date(2026, 11, 7))

    assert asyncio.run(flow()).client == "Заря"
    assert len(requests) == 2
    assert requests[1]["max_output_tokens"] == 12000
    assert requests[0]["text"]["format"]["strict"] is True
    assert "proposal_parse_incomplete" in caplog.text
    assert "proposal_parse_validation" not in caplog.text
    assert "PRIVATE CUSTOMER" not in caplog.text


def test_money_schema_avoids_decimal_decoding_constraints():
    from bp_bot.ai import proposal_format

    schema = proposal_format()["schema"]
    for props in (schema["properties"], schema["$defs"]["ItemInput"]["properties"]):
        assert props["unit_price"]["anyOf"] == [{"type": "string"}, {"type": "null"}]
    assert schema["$defs"]["ItemInput"]["properties"]["quantity"]["maximum"] == 1000


@pytest.mark.parametrize("price", ["0", "-1", "NaN", "1.001", "1000000000000"])
def test_simple_money_schema_keeps_domain_limits(price):
    import json

    invalid = response(
        raw=json.dumps({"items": [{"product_query": "A", "quantity": 1, "unit_price": price}]})
    )
    ai, create = configured_ai([invalid, invalid])
    with pytest.raises(BusinessError):
        asyncio.run(ai.parse("Сделай КП", date(2026, 11, 7)))
    assert create.await_count == 2


def test_money_string_keeps_exact_price_and_safe_delivery_terms():
    import json
    from decimal import Decimal

    result = response(
        raw=json.dumps(
            {
                "client": "ООО Заря",
                "items": [{"product_query": "Tomahawk 505M", "quantity": 1, "unit_price": "2730000.01"}],
                "delivery_terms": "6 рабочих дней",
                "valid_until": "2026-12-31",
                "forbidden_requests": [],
            }
        )
    )
    ai, _ = configured_ai([result])
    p = asyncio.run(ai.parse("Сделай КП", date(2026, 11, 7)))
    assert p.items[0].unit_price == Decimal("2730000.01")
    assert p.delivery_terms == "В течение 6 рабочих дней после полной оплаты."
