import asyncio
import io
import shutil
from datetime import date
from decimal import Decimal

import pytest
from docx import Document
from pydantic import ValidationError

from bp_bot.ai import parse_fields
from bp_bot.bot import format_view
from bp_bot.documents import generate
from bp_bot.domain import BusinessError, ItemInput, ProposalPatch
from bp_bot.proposal_document import build_proposal
from test_ai_recovery import configured_ai, response
from test_document_photos import letterhead
from test_quotes import patch


PAYMENTS = "20% до 30 декабря; 20% до 20 января; 20% до 20 февраля; 20% до 20 марта; 20% до 20 апреля."


@pytest.mark.parametrize("uid", [1, 2, 4])
def test_all_roles_edit_terms_and_discount_preserving_vat_and_history(service, uid, tmp_path):
    q = service.create(2, patch(), "original")["id"]
    service.finish(2, q, 1)
    service.revise(
        uid,
        q,
        1,
        ProposalPatch(
            payment_terms=PAYMENTS,
            delivery_terms="5 рабочих дней",
            discount_percent="10",
            collection="Доставка включена.",
            additional_terms="Гарантия 12 месяцев.",
        ),
        "terms",
    )
    v = service.view(uid, q)
    p = v["payload"]
    assert p["payment_terms"] == PAYMENTS
    assert p["totals"]["gross"] == "7515000.00"
    assert p["items"][0]["vat_rate"] == "22.00"
    assert p["totals"]["vat"] == "1355163.93"
    assert v["status"] == "draft"
    old = service.view(uid, q, 1)
    assert old["status"] == "finished"
    assert old["payload"]["payment_terms"] == "Предоплата 100%."
    assert old["payload"]["totals"]["gross"] == "8350000.00"
    rendered = format_view(v)
    target = tmp_path / "terms.docx"
    build_proposal(letterhead(), v, target)
    doc = "\n".join(p.text for p in Document(target).paragraphs)
    for output in (rendered, doc):
        assert PAYMENTS in output
        assert "Доставка включена." in output
        assert "Гарантия 12 месяцев." in output
        assert "Скидка: 10%" in output
        assert "100%" not in output and "после полной оплаты" not in output


def test_discount_revisions_do_not_compound_and_can_be_removed(service):
    q = service.create(2, patch(discount_percent=10), "a")["id"]
    for version, change in enumerate(
        [
            ProposalPatch(client="Другой"),
            ProposalPatch(discount_percent=10),
            ProposalPatch(discount_percent=20),
            ProposalPatch(unit_price=100),
            ProposalPatch(discount_percent=0),
        ],
        1,
    ):
        service.revise(2, q, version, change, f"edit{version}")
    amounts = [service.view(2, q, n)["payload"]["totals"]["gross"] for n in range(1, 7)]
    assert amounts == ["7515000.00", "7515000.00", "7515000.00", "6680000.00", "80.00", "100.00"]


def test_discount_applies_to_replaced_items_and_missing_prices(service):
    q = service.create(2, patch(items=[ItemInput(product_query="A", quantity=50)], discount_percent=5), "a")[
        "id"
    ]
    assert service.view(2, q)["payload"]["totals"]["gross"] is None
    service.revise(2, q, 1, ProposalPatch(unit_price=9900), "price")
    assert service.view(2, q)["payload"]["totals"]["gross"] == "470250.00"
    service.revise(
        2,
        q,
        2,
        ProposalPatch(
            items=[
                ItemInput(product_query="A", quantity=2, unit_price="1.01"),
                ItemInput(product_query="B", quantity=3, unit_price="10"),
            ]
        ),
        "replace",
    )
    p = service.view(2, q)["payload"]
    assert p["totals"]["gross"] == "30.42"
    assert all(i["vat_rate"] == "22.00" for i in p["items"])


def test_terms_do_not_expand_quote_access_or_tax_permissions(service):
    q = service.create(2, patch(), "a")["id"]
    for uid in (3, 999):
        with pytest.raises(BusinessError):
            service.revise(uid, q, 1, ProposalPatch(payment_terms=PAYMENTS), str(uid))
    for uid in (2, 4):
        with pytest.raises(BusinessError):
            service.revise(uid, q, 1, ProposalPatch(payment_terms=PAYMENTS), str(uid), vat=10, reason="test")
    assert service.view(2, q)["version"] == 1


@pytest.mark.parametrize("value", ["-1", "100.01", "1.001", "NaN", "Infinity"])
def test_discount_validation(value):
    with pytest.raises(ValidationError):
        ProposalPatch(discount_percent=value)


def test_structured_terms_and_tax_rejection():
    p = parse_fields(
        "оплата=20% аванс, 80% после поставки; доставка=Самовывоз; условия=Гарантия; скидка=5,5%"
    ).safe()
    assert p.discount_percent == Decimal("5.5")
    assert p.payment_terms == "20% аванс, 80% после поставки"
    with pytest.raises(BusinessError):
        parse_fields("НДС=10")


def test_recognized_installments_keep_all_dates_separate_from_validity(service):
    ai, _ = configured_ai(
        [
            response(
                ProposalPatch(
                    client="Заря, агрофирма ООО",
                    items=[ItemInput(product_query="A", quantity=50, unit_price=9900)],
                    payment_terms=PAYMENTS,
                    delivery_terms="5 рабочих дней",
                )
            )
        ]
    )
    p = asyncio.run(ai.parse("Клиент Заря. 50 штук, цена 9900. " + PAYMENTS, date(2026, 11, 24)))
    q = service.create(2, p, "recognized")["id"]
    v = service.view(2, q)
    assert v["payload"]["payment_terms"] == PAYMENTS
    assert v["payload"]["valid_until"] is None
    assert v["payload"]["totals"]["gross"] == "495000.00"


@pytest.mark.parametrize("uid", [1, 2, 4])
@pytest.mark.parametrize("voice", [False, True])
def test_telegram_terms_edit_after_text_or_voice_confirmation(service, tmp_path, uid, voice):
    from unittest.mock import AsyncMock
    from aiogram import Bot
    from aiogram.types import Update
    from bp_bot.bot import UI
    from bp_bot.config import Settings
    from bp_bot.storage import LocalStorage

    q = service.create(2, patch(), "before")["id"]
    ai, _ = configured_ai([response(ProposalPatch(payment_terms=PAYMENTS, delivery_terms="5 рабочих дней"))])
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    ui = UI(bot, service, ai, LocalStorage(tmp_path), settings)
    target = {"mode": "edit", "id": q, "version": 1}
    sender = {"id": uid, "is_bot": False, "first_name": "Test"}
    message = {"message_id": 99, "date": 1793275200, "chat": {"id": uid, "type": "private"}}
    if voice:
        ui.state(
            uid,
            {
                "mode": "voice",
                "text": PAYMENTS,
                "token": "terms",
                "request_key": f"voice:{uid}:99",
                "target": target,
            },
        )
        update = {
            "update_id": 99,
            "callback_query": {
                "id": "99",
                "chat_instance": "test",
                "data": "voice:terms",
                "from": sender,
                "message": {**message, "text": "Проверьте распознанный текст"},
            },
        }
    else:
        ui.state(uid, target)
        update = {"update_id": 99, "message": {**message, "from": sender, "text": PAYMENTS}}
    asyncio.run(ui.dp.feed_update(bot, Update.model_validate(update)))
    v = service.view(uid, q)
    assert v["version"] == 2
    assert v["payload"]["payment_terms"] == PAYMENTS
    assert v["payload"]["delivery_terms"] == "В течение 5 рабочих дней."
    assert ui.state(uid) is None


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_terms_render_actual_word_and_pdf(service):
    q = service.create(2, patch(payment_terms=PAYMENTS, discount_percent=5), "pdf")["id"]
    service.finish(2, q, 1)
    word, pdf = generate(letterhead(), service.view(2, q))
    assert pdf.startswith(b"%PDF-")
    assert PAYMENTS in "\n".join(p.text for p in Document(io.BytesIO(word)).paragraphs)
