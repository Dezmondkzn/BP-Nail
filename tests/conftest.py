from datetime import date
from decimal import Decimal
import os
import pytest
from bp_bot.models import Base, database
from bp_bot.service import Quotes


class Rates:
    def rate(self, currency, day):
        return (Decimal("100") if currency != "RUB" else Decimal(1), day)


@pytest.fixture
def service(tmp_path):
    # TEST_DATABASE_URL must reference a disposable DB. CI uses a dedicated Postgres service.
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    engine, sessions = database(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    svc = Quotes(sessions, Rates())
    svc.today = lambda: date(2026, 10, 29)
    svc.bootstrap(1, "Начальник")
    svc.set_user(1, 2, "manager", "main", "Менеджер 1")
    svc.set_user(1, 3, "manager", "other", "Менеджер 2")
    svc.set_user(1, 4, "sales_head", "main", "Руководитель")
    svc.import_catalog(
        1,
        (
            "sku,name,configuration,price,currency,supply,price_date,valid_until,vat_rate,active\n"
            "A,Бункер 401,Тент,8350000,RUB,stock,2026-09-17,2026-12-31,22,true\n"
            "B,Трактор 100,База,10000,EUR,order,2026-09-17,2026-12-31,22,true\n"
            "C,Трактор 100,С ВОМ,12000,EUR,order,2026-09-17,2026-12-31,22,true\n"
        ).encode(),
    )
    svc.set_letterhead(1, "letterheads/test.docx")
    yield svc
    engine.dispose()
