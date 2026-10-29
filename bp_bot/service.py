from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .models import User, Product, Quote, Version, Audit, AppValue, RequestReceipt, Job, now
from .domain import Role, BusinessError, authorize, money, totals, missing
from .catalog import match_product, parse_catalog


class Quotes:
    def __init__(self, sessions, rates, timezone="Europe/Moscow"):
        self.sessions = sessions
        self.rates = rates
        self.timezone = timezone

    def today(self):
        return datetime.now(ZoneInfo(self.timezone)).date()

    def user(self, uid):
        with self.sessions() as s:
            user = s.get(User, uid)
            authorize(user)
            return user

    def bootstrap(self, uid, name):
        if not uid:
            return
        with self.sessions.begin() as s:
            # Bootstrap once only. Never restore revoked privileges on restart.
            if not s.get(AppValue, "bootstrap_done"):
                if s.scalar(select(User.telegram_id).limit(1)) is None:
                    s.add(User(telegram_id=uid, name=name, role=Role.CHIEF, department="main"))
                s.add(AppValue(key="bootstrap_done", value={"done": True}))

    def set_user(self, actor_id, uid, role, department, name, active=True):
        if role not in set(Role) or uid <= 0 or not name.strip() or not department.strip():
            raise BusinessError("Проверьте ID, роль, отдел и имя.")
        if len(name) > 120 or len(department) > 80:
            raise BusinessError("Слишком длинное имя или отдел.")
        with self.sessions.begin() as s:
            authorize(s.get(User, actor_id), chief=True)
            if uid == actor_id and (role != Role.CHIEF or not active):
                raise BusinessError("Нельзя отключить или понизить самого себя.")
            user = s.get(User, uid)
            if user is None:
                user = User(telegram_id=uid)
                s.add(user)
            user.name, user.role, user.department, user.active = name, role, department, active
            s.add(
                Audit(
                    actor_id=actor_id,
                    action="set_user",
                    details={"user": uid, "role": role, "active": active},
                )
            )

    def users(self, actor_id):
        with self.sessions() as s:
            authorize(s.get(User, actor_id), chief=True)
            return list(s.scalars(select(User).order_by(User.name)))

    def import_catalog(self, uid, raw):
        authorize(self.user(uid), chief=True)
        rows = parse_catalog(raw)
        with self.sessions.begin() as s:
            authorize(s.get(User, uid), chief=True)
            for row in rows:
                data = row.model_dump(mode="json")
                p = s.get(Product, row.sku)
                if p is None:
                    p = Product(sku=row.sku)
                    s.add(p)
                for key, value in data.items():
                    setattr(p, key, value)
            s.add(Audit(actor_id=uid, action="catalog_import", details={"count": len(rows)}))
        return len(rows)

    def catalog(self, uid, query=""):
        self.user(uid)
        with self.sessions() as s:
            rows = list(s.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.sku)))
            return [p for p in rows if query.casefold() in (p.sku + " " + p.name).casefold()][:30]

    def set_letterhead(self, uid, key):
        with self.sessions.begin() as s:
            authorize(s.get(User, uid), chief=True)
            v = s.get(AppValue, "letterhead")
            if v:
                v.value = {"key": key}
            else:
                s.add(AppValue(key="letterhead", value={"key": key}))
            s.add(Audit(actor_id=uid, action="letterhead", details={"key": key}))

    def _items(self, s, requested):
        products = list(s.scalars(select(Product).where(Product.active.is_(True))))
        output, rates = [], {}
        for i in requested:
            p = match_product(products, i.product_query)
            if date.fromisoformat(p.valid_until) < self.today():
                raise BusinessError(f"Цена {p.sku} просрочена. Начальник должен обновить каталог.")
            if p.currency not in rates:
                rates[p.currency] = self.rates.rate(p.currency, self.today())
            rate, rate_date = rates[p.currency]
            unit = money(Decimal(str(p.price)) * rate)
            output.append(
                {
                    "sku": p.sku,
                    "name": p.name,
                    "configuration": p.configuration,
                    "quantity": i.quantity,
                    "source_price": str(p.price),
                    "currency": p.currency,
                    "price_date": p.price_date,
                    "price_valid_until": p.valid_until,
                    "supply": p.supply,
                    "rate": str(rate),
                    "rate_date": rate_date.isoformat(),
                    "unit_price": str(unit),
                    "line_total": str(money(unit * i.quantity)),
                    "vat_rate": str(p.vat_rate),
                }
            )
        return output

    def _apply(self, s, data, patch):
        patch.safe()
        for key in ("client", "delivery_terms", "valid_until"):
            val = getattr(patch, key)
            if val is not None:
                data[key] = val.isoformat() if isinstance(val, date) else val.strip()
        if patch.items is not None:
            if not patch.items:
                raise BusinessError("Укажите хотя бы одну позицию.")
            data["items"] = self._items(s, patch.items)
        if data.get("valid_until") and date.fromisoformat(data["valid_until"]) < self.today():
            raise BusinessError("Срок предложения не может быть в прошлом.")
        data["totals"] = totals(data.get("items", []))
        return data

    def create(self, uid, patch, request_key):
        try:
            with self.sessions.begin() as s:
                actor = s.get(User, uid)
                authorize(actor)
                receipt = s.get(RequestReceipt, request_key)
                if receipt:
                    return receipt.result
                letterhead = s.get(AppValue, "letterhead")
                data = self._apply(
                    s,
                    {
                        "client": "",
                        "items": [],
                        "delivery_terms": "",
                        "valid_until": None,
                        "manager": actor.name,
                        "prepayment": 100,
                        "collection": "Самовывоз. Доставка в стоимость не включена.",
                        "letterhead_key": letterhead.value["key"] if letterhead else None,
                        "template_version": "1",
                    },
                    patch,
                )
                q = Quote(owner_id=uid, department=actor.department)
                s.add(q)
                s.flush()
                v = Version(quote_id=q.id, number=1, payload=data, created_by=uid)
                s.add(v)
                result = {"id": q.id, "version": 1}
                s.add(RequestReceipt(key=request_key, result=result))
                s.add(Audit(actor_id=uid, action="create", quote_id=q.id, details={"version": 1}))
                return result
        except IntegrityError:
            with self.sessions() as s:
                receipt = s.get(RequestReceipt, request_key)
                if receipt:
                    return receipt.result
            raise

    def _get(self, s, uid, qid, number=None):
        q = s.get(Quote, qid)
        if q is None:
            raise BusinessError("КП не найдено.")
        authorize(s.get(User, uid), q)
        v = s.scalar(
            select(Version).where(Version.quote_id == qid, Version.number == (number or q.current_version))
        )
        if v is None:
            raise BusinessError("Версия не найдена.")
        return q, v

    def view(self, uid, qid, number=None):
        with self.sessions() as s:
            q, v = self._get(s, uid, qid, number)
            return {
                "id": q.id,
                "version": v.number,
                "current_version": q.current_version,
                "status": v.status,
                "payload": v.payload,
                "created_at": v.created_at.isoformat(),
                "missing": missing(v.payload, self.today()),
            }

    def list_quotes(self, uid):
        with self.sessions() as s:
            u = s.get(User, uid)
            authorize(u)
            stmt = select(Quote).order_by(Quote.id.desc()).limit(30)
            if u.role == Role.MANAGER:
                stmt = stmt.where(Quote.owner_id == uid)
            elif u.role == Role.SALES_HEAD:
                stmt = stmt.where(Quote.department == u.department)
            return [{"id": q.id, "version": q.current_version} for q in s.scalars(stmt)]

    def history(self, uid, qid):
        with self.sessions() as s:
            self._get(s, uid, qid)
            return [
                {
                    "version": v.number,
                    "status": v.status,
                    "actor": v.created_by,
                    "created": v.created_at.isoformat(),
                }
                for v in s.scalars(select(Version).where(Version.quote_id == qid).order_by(Version.number))
            ]

    def revise(self, uid, qid, expected, patch, request_key, vat=None, reason=None):
        try:
            with self.sessions.begin() as s:
                q, old = self._get(s, uid, qid)
                receipt = s.get(RequestReceipt, request_key)
                if receipt:
                    return receipt.result
                if q.current_version != expected:
                    raise BusinessError("КП уже изменено. Откройте /show и используйте текущую версию.")
                if vat is not None:
                    authorize(s.get(User, uid), chief=True)
                    vat = Decimal(str(vat))
                    if not vat.is_finite() or not 0 <= vat <= 100 or vat != money(vat) or not reason:
                        raise BusinessError("Укажите НДС от 0 до 100% и причину изменения.")
                data = self._apply(s, deepcopy(old.payload), patch)
                # Attach a newly supplied letterhead only to a NEW version.
                if not data.get("letterhead_key"):
                    head = s.get(AppValue, "letterhead")
                    data["letterhead_key"] = head.value["key"] if head else None
                if vat is not None:
                    for item in data["items"]:
                        item["vat_rate"] = str(vat)
                    data["vat_override_reason"] = reason[:500]
                    data["totals"] = totals(data["items"])
                changed = s.execute(
                    update(Quote)
                    .where(Quote.id == qid, Quote.current_version == expected)
                    .values(current_version=expected + 1)
                )
                if changed.rowcount != 1:
                    raise BusinessError("КП изменено другим пользователем. Обновите карточку.")
                s.add(Version(quote_id=qid, number=expected + 1, payload=data, created_by=uid))
                result = {"id": qid, "version": expected + 1}
                s.add(RequestReceipt(key=request_key, result=result))
                s.add(
                    Audit(
                        actor_id=uid,
                        action="vat_override" if vat is not None else "revise",
                        quote_id=qid,
                        details={"version": expected + 1, "reason": reason},
                    )
                )
                return result
        except IntegrityError:
            with self.sessions() as s:
                receipt = s.get(RequestReceipt, request_key)
                if receipt:
                    return receipt.result
            raise BusinessError("Конфликт изменений. Обновите карточку.") from None

    def finish(self, uid, qid, number):
        with self.sessions.begin() as s:
            # Serialize finishing with version creation. The revision CAS locks this same row.
            s.execute(select(Quote).where(Quote.id == qid).with_for_update()).scalar_one_or_none()
            q, v = self._get(s, uid, qid, number)
            if number != q.current_version:
                raise BusinessError("Завершить можно только текущую версию.")
            if v.status == "finished":
                return
            gaps = missing(v.payload, self.today())
            if gaps:
                raise BusinessError("Нужно заполнить: " + "; ".join(gaps))
            if any(date.fromisoformat(i["price_valid_until"]) < self.today() for i in v.payload["items"]):
                raise BusinessError("Срок цены истёк. Обновите каталог и позиции новой версии.")
            v.status, v.finished_by, v.finished_at = "finished", uid, now()
            s.add(Audit(actor_id=uid, action="finish", quote_id=qid, details={"version": number}))

    def request_files(self, uid, qid, number):
        with self.sessions.begin() as s:
            q, v = self._get(s, uid, qid, number)
            if v.status != "finished":
                raise BusinessError("Сначала проверьте и завершите эту версию КП.")
            job = s.scalar(select(Job).where(Job.version_id == v.id))
            if not job:
                job = Job(version_id=v.id)
                s.add(job)
                s.flush()
            elif job.state == "failed":
                job.state, job.attempts, job.error = "queued", 0, None
            return {"state": job.state, "docx_key": job.docx_key, "pdf_key": job.pdf_key}
