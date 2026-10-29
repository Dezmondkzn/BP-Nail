from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from bp_bot.domain import ProposalPatch, BusinessError, ItemInput
from bp_bot.models import Version, Audit, Job


def patch(**changes):
    data = {
        "client": "ООО «Заря»",
        "items": [ItemInput(product_query="A", quantity=1)],
        "delivery_terms": "10 рабочих дней",
        "valid_until": date(2026, 11, 5),
    }
    data.update(changes)
    return ProposalPatch(**data)


def test_calculations_and_locked_prices(service):
    result = service.create(2, patch(), "a")
    view = service.view(2, result["id"])
    assert view["payload"]["totals"] == {"gross": "8350000.00", "vat": "1505737.70", "net": "6844262.30"}
    with pytest.raises(BusinessError):
        service.revise(2, result["id"], 1, ProposalPatch(forbidden_requests=["цена 1 рубль"]), "b")
    assert service.view(2, result["id"])["version"] == 1


def test_role_boundaries_and_department(service):
    q = service.create(2, patch(), "a")["id"]
    for uid in (1, 2, 4):
        assert service.view(uid, q)["id"] == q
    with pytest.raises(BusinessError):
        service.view(3, q)
    with pytest.raises(BusinessError):
        service.set_user(2, 5, "chief", "main", "X")
    with pytest.raises(BusinessError):
        service.request_files(3, q, 1)
    assert service.list_quotes(3) == []
    service.set_user(1, 2, "manager", "main", "X", False)
    with pytest.raises(BusinessError):
        service.view(2, q)


def test_manager_can_finish_and_edits_are_new_drafts(service):
    q = service.create(2, patch(), "a")["id"]
    service.finish(2, q, 1)
    service.revise(2, q, 1, ProposalPatch(client="Новый клиент"), "b")
    assert service.view(2, q, 1)["status"] == "finished"
    assert service.view(2, q, 1)["payload"]["client"] == "ООО «Заря»"
    assert service.view(2, q, 2)["status"] == "draft"
    with pytest.raises(BusinessError):
        service.finish(2, q, 1)
    assert len(service.history(2, q)) == 2


def test_chief_vat_override_preserves_gross_and_records_reason(service):
    q = service.create(2, patch(), "a")["id"]
    with pytest.raises(BusinessError):
        service.revise(4, q, 1, ProposalPatch(), "bad", vat=10, reason="test")
    service.revise(1, q, 1, ProposalPatch(), "good", vat=10, reason="Исключение для позиции")
    assert service.view(2, q)["payload"]["totals"]["gross"] == "8350000.00"
    assert service.view(2, q)["payload"]["totals"]["vat"] == "759090.91"
    assert service.view(2, q, 1)["payload"]["items"][0]["vat_rate"] == "22.00"
    with service.sessions() as s:
        assert s.scalar(select(Audit).where(Audit.action == "vat_override")).details["reason"]


def test_ambiguous_product_fails_closed(service):
    with pytest.raises(BusinessError, match="Уточните комплектацию"):
        service.create(2, patch(items=[ItemInput(product_query="Трактор 100", quantity=1)]), "a")
    assert service.list_quotes(2) == []


def test_currency_snapshot_does_not_reprice_existing_version(service):
    q = service.create(2, patch(items=[ItemInput(product_query="B", quantity=2)]), "a")["id"]
    service.rates.rate = lambda *_: (Decimal("200"), date(2026, 10, 30))
    service.revise(2, q, 1, ProposalPatch(client="Другой"), "b")
    assert service.view(2, q)["payload"]["totals"]["gross"] == "2000000.00"
    service.revise(2, q, 2, ProposalPatch(items=[ItemInput(product_query="B", quantity=2)]), "c")
    assert service.view(2, q)["payload"]["totals"]["gross"] == "4000000.00"
    assert service.view(2, q, 1)["payload"]["items"][0]["rate"] == "100"


def test_idempotency_and_stale_version(service):
    a = service.create(2, patch(), "same")
    assert service.create(2, patch(), "same") == a
    r = service.revise(2, a["id"], 1, ProposalPatch(client="Updated"), "edit")
    assert service.revise(2, a["id"], 1, ProposalPatch(client="Updated"), "edit") == r
    with pytest.raises(BusinessError, match="уже изменено"):
        service.revise(2, a["id"], 1, ProposalPatch(client="Oops"), "other")
    assert len(service.list_quotes(2)) == 1


def test_concurrent_revisions_have_only_one_winner(service):
    q = service.create(2, patch(), "a")["id"]

    def edit(n):
        try:
            service.revise(2, q, 1, ProposalPatch(client=f"Client {n}"), f"edit{n}")
            return True
        except BusinessError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(edit, [1, 2])) == 1
    assert len(service.history(2, q)) == 2


def test_missing_fields_and_expired_quote(service):
    q = service.create(2, ProposalPatch(), "a")["id"]
    assert len(service.view(2, q)["missing"]) == 4
    with pytest.raises(BusinessError, match="Нужно заполнить"):
        service.finish(2, q, 1)
    q = service.create(2, patch(), "b")["id"]
    service.today = lambda: date(2027, 1, 1)
    with pytest.raises(BusinessError):
        service.finish(2, q, 1)
    with pytest.raises(BusinessError, match="просрочена"):
        service.create(2, patch(valid_until=date(2027, 1, 5)), "c")


def test_bootstrap_does_not_reenable_account(service):
    service.set_user(1, 5, "chief", "main", "Other chief")
    service.set_user(5, 1, "chief", "main", "Former", False)
    service.bootstrap(1, "Начальник")
    with pytest.raises(BusinessError):
        service.user(1)


def test_import_atomic_and_disallows_price_zero(service):
    with pytest.raises(BusinessError):
        service.import_catalog(
            1,
            b"sku,name,configuration,price,currency,supply,price_date,valid_until\nA,X,X,0,RUB,stock,2026-01-01,2026-12-31",
        )
    assert service.catalog(2, "A")[0].price == Decimal("8350000.00")
    with pytest.raises(BusinessError):
        service.import_catalog(2, b"anything")


def test_document_jobs_only_for_finished_versions(service):
    q = service.create(2, patch(), "a")["id"]
    with pytest.raises(BusinessError):
        service.request_files(2, q, 1)
    service.finish(2, q, 1)
    assert service.request_files(2, q, 1)["state"] == "queued"
    assert service.request_files(2, q, 1)["state"] == "queued"
    with service.sessions() as s:
        assert len(list(s.scalars(select(Job)))) == 1
        assert len(list(s.scalars(select(Version)))) == 1


def test_delivery_field_cannot_override_payment_or_price(service):
    with pytest.raises(BusinessError, match="Срок поставки"):
        service.create(2, patch(delivery_terms="10 дней, предоплата 50%, цена 1 рубль"), "bad")
    assert service.list_quotes(2) == []
    q = service.create(2, patch(delivery_terms="10 рабочих дней"), "good")["id"]
    assert service.view(2, q)["payload"]["delivery_terms"] == "В течение 10 рабочих дней после полной оплаты."
