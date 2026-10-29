import csv
import io
import re
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from .domain import BusinessError


class CatalogRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=300)
    configuration: str = Field(min_length=1, max_length=3000)
    price: Decimal = Field(gt=0, le=Decimal("999999999999.99"), decimal_places=2)
    currency: str = Field(pattern=r"^(RUB|EUR|USD|CNY)$")
    supply: str = Field(pattern=r"^(stock|paid|order)$")
    price_date: date
    valid_until: date
    vat_rate: Decimal = Field(default=Decimal(22), ge=0, le=100, decimal_places=2)
    active: bool = True


def parse_catalog(raw: bytes):
    if len(raw) > 2_000_000:
        raise BusinessError("CSV слишком большой (максимум 2 МБ).")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        rows = [CatalogRow.model_validate(r) for r in reader]
        if not 1 <= len(rows) <= 2000:
            raise ValueError()
        if len({r.sku for r in rows}) != len(rows):
            raise ValueError()
        for r in rows:
            if r.supply in {"stock", "paid"} and r.currency != "RUB":
                raise ValueError()
            if r.price_date > r.valid_until:
                raise ValueError()
        return rows
    except (ValueError, UnicodeError):
        raise BusinessError(
            "CSV не принят. Проверьте колонки, уникальность SKU, положительные цены, "
            "даты и валюту RUB для stock/paid. Импорт выполняется целиком."
        ) from None


def normalized(s):
    return re.sub(r"[^\w]+", " ", s.casefold()).strip()


def match_product(products, query):
    exact = [p for p in products if p.sku.casefold() == query.casefold()]
    if exact:
        return exact[0]
    q = normalized(query)
    candidates = [p for p in products if q and q in normalized(p.name + " " + p.configuration)]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        options = "; ".join(f"{p.sku}: {p.name}" for p in candidates[:8])
        raise BusinessError("Уточните комплектацию и укажите SKU: " + options)
    raise BusinessError("Техника не найдена. Откройте /catalog и укажите точный SKU.")
