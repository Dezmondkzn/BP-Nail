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


# A single spelling space for Russian voice transcripts and Latin model names.
_TRANSLIT = str.maketrans(
    dict(
        zip(
            "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
            [
                "a",
                "b",
                "v",
                "g",
                "d",
                "e",
                "e",
                "zh",
                "z",
                "i",
                "i",
                "k",
                "l",
                "m",
                "n",
                "o",
                "p",
                "r",
                "s",
                "t",
                "u",
                "f",
                "h",
                "ts",
                "ch",
                "sh",
                "sch",
                "",
                "y",
                "",
                "e",
                "yu",
                "ya",
            ],
        )
    )
)


def normalized(s):
    s = s.casefold().translate(_TRANSLIT)
    s = re.sub(r"([a-z])(\d)|(?<=\d)(?=[a-z])", lambda m: m[1] + " " + m[2] if m[1] else " ", s)
    return " ".join(re.findall(r"[a-z]+|\d+", s))


class ProductChoice(BusinessError):
    def __init__(self, query, products):
        self.query = query
        self.products = products[:8]
        super().__init__("Уточните комплектацию: выберите подходящую технику.")


def word_similarity(left, right):
    from difflib import SequenceMatcher

    # Inflected configuration words are suggestions, never exact auto-selections.
    endings = ("aya", "uyu", "ogo", "omu", "ymi", "oi", "yi", "ye", "ym", "a", "y", "e", "u")

    def stems(word):
        return {word[: -len(end)] for end in endings if word.endswith(end) and len(word) - len(end) >= 5}

    if stems(left) & stems(right):
        return 0.9
    return SequenceMatcher(None, left, right).ratio()


def search_products(products, query):

    products = [p for p in products if p.active]
    query = query.strip()
    exact = [p for p in products if p.sku.casefold() == query.casefold()]
    if exact:
        return exact, True
    words = [w for w in normalized(query).split() if w not in {"s", "so", "i"}]
    if not words:
        return [], False
    numbers = {w for w in words if w.isdigit()}
    ranked = []
    for p in products:
        name = normalized(p.name).split()
        # Never turn a mistyped model number into a different model.
        if not numbers.issubset(set(name)):
            continue
        tokens = set(name + normalized(p.configuration).split())
        scores = [
            1.0
            if w in tokens
            else max(
                (
                    word_similarity(w, t)
                    for t in tokens
                    if not w.isdigit() and not t.isdigit() and min(len(w), len(t)) >= 4
                ),
                default=0,
            )
            for w in words
        ]
        if min(scores) >= 0.72:
            ranked.append((sum(scores) / len(scores), p))
    ranked.sort(key=lambda row: (-row[0], row[1].sku))
    exact = [p for score, p in ranked if score == 1]
    if exact:
        return exact, True
    return [p for _, p in ranked], False


def match_product(products, query):
    candidates, exact = search_products(products, query)
    if len(candidates) == 1 and exact:
        return candidates[0]
    if candidates:
        raise ProductChoice(query, candidates)
    raise BusinessError(
        "Техника не найдена. Укажите марку и модель без дополнительных слов "
        "или найдите её через /catalog название."
    )
