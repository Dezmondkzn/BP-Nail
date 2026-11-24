from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
import re
from pydantic import BaseModel, ConfigDict, Field


class BusinessError(ValueError):
    pass


class Role(StrEnum):
    MANAGER = "manager"
    SALES_HEAD = "sales_head"
    CHIEF = "chief"


def authorize(user, quote=None, chief=False):
    if not user or not user.active:
        raise BusinessError("Доступ закрыт. Обратитесь к начальнику.")
    if chief and user.role != Role.CHIEF:
        raise BusinessError("Это действие доступно только начальнику.")
    if quote and not (
        user.role == Role.CHIEF
        or quote.owner_id == user.telegram_id
        or (user.role == Role.SALES_HEAD and user.department == quote.department)
    ):
        raise BusinessError("Нет доступа к этому КП.")


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_query: str = Field(min_length=1, max_length=300)
    quantity: int = Field(ge=1, le=1000, strict=True)
    unit_price: Decimal | None = Field(default=None, gt=0, le=Decimal("999999999999.99"), decimal_places=2)


class ProposalPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_price: Decimal | None = Field(default=None, gt=0, le=Decimal("999999999999.99"), decimal_places=2)
    client: str | None = Field(default=None, max_length=300)
    items: list[ItemInput] | None = Field(default=None, max_length=20)
    delivery_terms: str | None = Field(default=None, max_length=500)
    payment_terms: str | None = Field(default=None, min_length=1, max_length=1500)
    collection: str | None = Field(default=None, min_length=1, max_length=500)
    additional_terms: str | None = Field(default=None, max_length=1000)
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100, decimal_places=2)
    valid_until: date | None = None
    forbidden_requests: list[str] = Field(default_factory=list, max_length=20)

    def safe(self):
        if self.forbidden_requests:
            raise BusinessError(
                "Условия оплаты, поставки и скидку можно менять всем ролям. "
                "Нельзя менять через текст КП менеджера, права доступа и реквизиты продавца. "
                "НДС уже включён в цену; изменение ставки — только начальником через /vat."
            )
        if self.delivery_terms is not None:
            text = self.delivery_terms.casefold().strip().rstrip(".")
            match = re.fullmatch(
                r"(?:в течение )?(\d{1,3}) (рабочих |календарных )?(?:дней|дня|день)"
                r"( после (?:поступления )?(?:полной )?оплаты)?",
                text,
            )
            if match:
                if not 1 <= int(match[1]) <= 730:
                    raise BusinessError("Срок поставки должен быть от 1 до 730 дней.")
                kind = (match[2] or "календарных ").strip()
                self.delivery_terms = f"В течение {int(match[1])} {kind} дней{match[3] or ''}."
        for key in ("payment_terms", "collection", "delivery_terms", "additional_terms"):
            value = getattr(self, key)
            if value is not None:
                value = value.strip()
                if not value and key != "additional_terms":
                    raise BusinessError("Условия не могут быть пустыми.")
                setattr(self, key, value)
        return self


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def totals(items):
    if any(i.get("unit_price") is None or i.get("line_total") is None for i in items):
        return {"gross": None, "vat": None, "net": None}
    gross = sum((Decimal(i["line_total"]) for i in items), Decimal(0))
    vat = sum(
        (
            money(Decimal(i["line_total"]) * Decimal(i["vat_rate"]) / (100 + Decimal(i["vat_rate"])))
            for i in items
        ),
        Decimal(0),
    )
    return {"gross": str(money(gross)), "vat": str(money(vat)), "net": str(money(gross - vat))}


def missing(payload, today):
    fields = []
    if not payload.get("client", "").strip():
        fields.append("клиент")
    if not payload.get("items"):
        fields.append("техника и количество (выберите SKU из /catalog)")
    for item in payload.get("items", []):
        if item.get("unit_price") is None or item.get("pricing_source") != "manager":
            fields.append(f"цена за единицу в рублях с НДС: {item['name']}")
    if not payload.get("delivery_terms", "").strip():
        fields.append("срок поставки")
    if not payload.get("valid_until"):
        fields.append("срок предложения (ГГГГ-ММ-ДД)")
    elif date.fromisoformat(payload["valid_until"]) < today:
        fields.append("срок предложения истёк")
    if not payload.get("letterhead_key"):
        fields.append("фирменный бланк (загрузите DOCX с подписью /letterhead)")
    return fields
