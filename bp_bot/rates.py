from datetime import date, datetime
from decimal import Decimal
import httpx
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from .domain import BusinessError


class CBR:
    def __init__(self, transport=None):
        self.transport = transport

    def rate(self, currency: str, day: date):
        if currency == "RUB":
            return Decimal(1), day
        try:
            with httpx.Client(timeout=15, transport=self.transport) as client:
                r = client.get(
                    "https://www.cbr.ru/scripts/XML_daily.asp", params={"date_req": day.strftime("%d/%m/%Y")}
                )
                r.raise_for_status()
            root = fromstring(r.content)
            effective = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
            if effective > day or (day - effective).days > 14:
                raise ValueError("Unexpected rate date")
            for row in root.findall("Valute"):
                if row.findtext("CharCode") == currency:
                    value = Decimal(row.findtext("Value").replace(",", "."))
                    nominal = Decimal(row.findtext("Nominal"))
                    if value <= 0 or nominal <= 0:
                        raise ValueError("Invalid rate")
                    return value / nominal, effective
        except (httpx.HTTPError, ValueError, ArithmeticError, KeyError, ParseError, DefusedXmlException):
            raise BusinessError("Не удалось получить курс ЦБ. Повторите позже; цена не рассчитана.") from None
        raise BusinessError("Валюта не найдена в курсе ЦБ.")
