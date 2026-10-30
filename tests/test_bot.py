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


def test_product_choice_preserves_request_and_rejects_stale_buttons(service, tmp_path):
    settings = Settings(
        bot_token="123456:TEST", database_url="sqlite://", app_env="development", storage_backend="local"
    )
    bot = Bot("123456:TEST")
    bot.session = AsyncMock()
    ui = UI(bot, service, AI(settings), LocalStorage(tmp_path), settings)

    async def click(data, number):
        await ui.dp.feed_update(
            bot,
            Update.model_validate(
                {
                    "update_id": number,
                    "callback_query": {
                        "id": str(number),
                        "chat_instance": "test",
                        "data": data,
                        "from": {"id": 2, "is_bot": False, "first_name": "Test"},
                        "message": {
                            "message_id": 99,
                            "date": 1793275200,
                            "chat": {"id": 2, "type": "private"},
                            "text": "Выберите",
                        },
                    },
                }
            ),
        )

    async def flow():
        from aiogram.types import Message

        message = Message.model_validate(
            {"message_id": 98, "date": 1793275200, "chat": {"id": 2, "type": "private"}}
        ).as_(bot)
        await ui.submit(
            message,
            "клиент=Заря; позиции=Трактоор 100:2,Бункер 401:3; поставка=10 дней; до=2026-12-01",
            "search-test",
            None,
        )
        assert service.list_quotes(2) == []
        st = ui.state(2)
        data = f"product:{st['token']}:1"
        await click(data, 200)
        q = service.list_quotes(2)[0]["id"]
        payload = service.view(2, q)["payload"]
        assert payload["client"] == "Заря"
        assert [(i["sku"], i["quantity"]) for i in payload["items"]] == [("C", 2), ("A", 3)]
        assert payload["valid_until"] == "2026-12-01"
        await click(data, 201)
        assert "уже обработан" in bot.session.call_args.args[1].text
        assert len(service.list_quotes(2)) == 1

    asyncio.run(flow())


def test_search_spelling_variants_and_model_safety(service):
    from types import SimpleNamespace
    import pytest
    from bp_bot.catalog import match_product, ProductChoice
    from bp_bot.domain import BusinessError

    p = SimpleNamespace(sku="X", name="Бункер GRITAN БНП-401", configuration="Тент", active=True)
    for query in ("Гритан БНП401", "gritan bnp 401", "401 gritan", "X"):
        assert match_product([p], query) is p
    with pytest.raises(ProductChoice):
        match_product([p], "Гриттан БНП 401")
    with pytest.raises(BusinessError, match="не найдена"):
        match_product([p], "GRITAN БНП402")
    p.active = False
    with pytest.raises(BusinessError, match="не найдена"):
        match_product([p], "X")
    assert [p.sku for p in service.catalog(2, "Трактоор 100")] == ["B", "C"]


def test_voice_configuration_inflections():
    from types import SimpleNamespace
    import pytest
    from bp_bot.catalog import search_products, match_product, ProductChoice
    from bp_bot.domain import BusinessError

    p = SimpleNamespace(
        sku="AT26-93C65E2C7D10",
        name="GRITAN Бункер накопитель БНП 301",
        configuration="Гидр. шиберные заслонки; Гидр.-расскладной склиз шнека; Тентовая система.",
        active=True,
    )
    query = "«Гритан» бункер-накопитель BNP-301 с тентовой системой"
    assert search_products([p], query) == ([p], False)
    with pytest.raises(ProductChoice) as choice:
        match_product([p], query)
    assert choice.value.products == [p]
    assert match_product([p], p.sku) is p
    for wrong in (query.replace("301", "401"), query.replace("с тентовой", "без тентовой"), "с и со"):
        with pytest.raises(BusinessError, match="не найдена"):
            match_product([p], wrong)
