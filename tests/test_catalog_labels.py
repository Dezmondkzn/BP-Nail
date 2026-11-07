import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Message

from bp_bot.bot import UI
from bp_bot.catalog import match_product
from bp_bot.config import Settings
from bp_bot.domain import BusinessError, ProposalPatch
from bp_bot.models import Product
from bp_bot.storage import LocalStorage


NAME = "GRITAN Бункер накопитель БНП 401 (в наличии)"
CONFIGURATION = "Гидр. шиберные заслонки; Гидр.-расскладной склиз шнека; Тентовая система."
SKU = "AT26-CB1CDC0F23D1"


@pytest.mark.parametrize(
    "label", ["модель ", "Модель: ", "марка=", "техника ", "оборудование: ", "модель: марка "]
)
def test_introductory_label_does_not_hide_catalog_product(label):
    product = SimpleNamespace(sku=SKU, name=NAME, configuration=CONFIGURATION, active=True)
    assert match_product([product], label + "GRITAN Бункер-накопитель БНП-401") is product


def test_labels_do_not_remove_model_or_configuration_requirements():
    product = SimpleNamespace(sku=SKU, name=NAME, configuration=CONFIGURATION, active=True)
    for query in ("модель GRITAN БНП-402", "модель GRITAN БНП-401 без тентовой системы"):
        with pytest.raises(BusinessError, match="Техника не найдена"):
            match_product([product], query)


def test_exact_reported_request_creates_quote_with_live_extracted_fields(service, tmp_path):
    with service.sessions.begin() as s:
        s.add(
            Product(
                sku=SKU,
                name=NAME,
                configuration=CONFIGURATION,
                active=True,
                currency="RUB",
                supply="stock",
                vat_rate=22,
            )
        )
    patch = ProposalPatch.model_validate(
        {
            "unit_price": "8350000.00",
            "client": 'ООО "Хрень"',
            "items": [
                {
                    "product_query": "модель GRITAN Бункер-накопитель БНП-401",
                    "quantity": 1,
                    "unit_price": "8350000.00",
                }
            ],
            "delivery_terms": "10 рабочих дней",
            "valid_until": "2026-11-20",
            "forbidden_requests": [],
        }
    )
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    ai = SimpleNamespace(parse=AsyncMock(return_value=patch))
    ui = UI(bot, service, ai, LocalStorage(tmp_path), settings)

    async def flow():
        message = Message.model_validate(
            {"message_id": 800, "date": 1793275200, "chat": {"id": 2, "type": "private"}}
        ).as_(bot)
        await ui.submit(
            message,
            'Создай коммерческое предложение для ООО "Хрень" модель GRITAN Бункер-накопитель БНП-401, цена 8 350 000, поставка в течение 10 рабочих дней, предложение до 20 ноября.',
            "reported-request",
            None,
        )
        quote = service.list_quotes(2)[0]
        payload = service.view(2, quote["id"])["payload"]
        assert payload["client"] == 'ООО "Хрень"'
        assert payload["items"][0]["sku"] == SKU
        assert payload["items"][0]["unit_price"] == "8350000.00"
        assert payload["totals"]["gross"] == "8350000.00"
        assert payload["valid_until"] == "2026-11-20"
        assert payload["delivery_terms"] == "В течение 10 рабочих дней после полной оплаты."
        assert ui.state(2) is None

    asyncio.run(flow())
