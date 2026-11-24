"""Validated secretary drafts and a private, durable protocol archive."""

from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .domain import BusinessError, authorize
from .models import AppValue, Audit, MeetingProtocol, ProtocolTask, RequestReceipt, User


class TaskDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: str = Field(min_length=1, max_length=1000)
    assignee: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    due_text: str | None = Field(default=None, max_length=200)


class ProtocolDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    meeting_date: date | None = None
    client: str | None = Field(default=None, max_length=500)
    participants: str | None = Field(default=None, max_length=1000)
    subject: str | None = Field(default=None, max_length=500)
    wishes: str | None = Field(default=None, max_length=2000)
    agreements: str | None = Field(default=None, max_length=3000)
    open_questions: str | None = Field(default=None, max_length=2000)
    tasks: list[TaskDraft] = Field(default_factory=list, max_length=30)


def protocol_schema():
    schema = ProtocolDraft.model_json_schema()

    def strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["required"] = list(node.get("properties", {}))
                node["additionalProperties"] = False
            for value in node.values():
                strict(value)
        elif isinstance(node, list):
            for value in node:
                strict(value)

    strict(schema)
    return schema


def format_protocol(payload):
    # Preserve unfinished drafts made before the structured schema was introduced.
    if isinstance(payload, str):
        return payload
    if payload.get("legacy_text") is not None:
        return payload["legacy_text"]
    fields = {
        "meeting_date": "Дата",
        "client": "Клиент",
        "participants": "Участники",
        "subject": "Тема",
        "wishes": "Пожелания клиента",
        "agreements": "Договорённости",
        "open_questions": "Открытые вопросы",
    }
    lines = [f"{label}: {payload.get(key) or '—'}" for key, label in fields.items()]
    lines.append("\nЗадачи:")
    for index, task in enumerate(payload.get("tasks", []), 1):
        due = task.get("due_date") or task.get("due_text") or "не указан"
        if task.get("due_date") and task.get("due_text"):
            due += f" ({task['due_text']})"
        lines.append(
            f"{index}. {task['action']}\nОтветственный: {task.get('assignee') or 'не указан'}; срок: {due}"
        )
    if not payload.get("tasks"):
        lines.append("Не указаны.")
    return "\n".join(lines)


class Secretary:
    PAGE_SIZE = 10

    def __init__(self, sessions):
        self.sessions = sessions

    def confirm(self, uid, token):
        key = f"protocol:{uid}:{token}"
        try:
            with self.sessions.begin() as s:
                authorize(s.get(User, uid))
                receipt = s.get(RequestReceipt, key)
                if receipt:
                    return receipt.result["protocol_id"]
                state = s.scalar(
                    select(AppValue).where(AppValue.key == f"conversation:{uid}").with_for_update()
                )
                data = state.value if state else {}
                if data.get("mode") != "secretary" or data.get("token") != token or not data.get("draft"):
                    receipt = s.get(RequestReceipt, key)
                    if receipt:
                        return receipt.result["protocol_id"]
                    raise BusinessError("Эта кнопка устарела. Используйте последнюю карточку.")
                if data.get("kind") not in {"Встреча", "Звонок"}:
                    raise BusinessError("Выберите встречу или звонок через /secretary.")
                draft = data["draft"]
                if isinstance(draft, str):
                    payload, tasks = {"legacy_text": draft}, []
                else:
                    validated = ProtocolDraft.model_validate(draft)
                    payload = validated.model_dump(mode="json", exclude={"tasks"})
                    tasks = validated.tasks
                record = MeetingProtocol(owner_id=uid, kind=data["kind"], payload=payload)
                s.add(record)
                s.flush()
                for position, task in enumerate(tasks, 1):
                    s.add(ProtocolTask(protocol_id=record.id, position=position, **task.model_dump()))
                s.add(RequestReceipt(key=key, result={"protocol_id": record.id}))
                s.add(Audit(actor_id=uid, action="protocol_confirm", details={"protocol_id": record.id}))
                s.delete(state)
                return record.id
        except IntegrityError:
            # A concurrent retry must return the same saved protocol, not a duplicate.
            with self.sessions() as s:
                authorize(s.get(User, uid))
                receipt = s.get(RequestReceipt, key)
                if receipt:
                    return receipt.result["protocol_id"]
            raise BusinessError("Не удалось сохранить протокол. Повторите подтверждение.") from None

    def list(self, uid, page=0):
        if not 0 <= page <= 100000:
            raise BusinessError("Некорректная страница архива.")
        with self.sessions() as s:
            authorize(s.get(User, uid))
            rows = list(
                s.scalars(
                    select(MeetingProtocol)
                    .where(MeetingProtocol.owner_id == uid)
                    .order_by(MeetingProtocol.id.desc())
                    .offset(page * self.PAGE_SIZE)
                    .limit(self.PAGE_SIZE + 1)
                )
            )
            return {
                "page": page,
                "has_next": len(rows) > self.PAGE_SIZE,
                "items": [
                    {
                        "id": row.id,
                        "kind": row.kind,
                        "client": row.payload.get("client"),
                        "subject": row.payload.get("subject"),
                        "meeting_date": row.payload.get("meeting_date"),
                    }
                    for row in rows[: self.PAGE_SIZE]
                ],
            }

    def view(self, uid, protocol_id):
        with self.sessions() as s:
            authorize(s.get(User, uid))
            record = s.scalar(
                select(MeetingProtocol).where(
                    MeetingProtocol.id == protocol_id, MeetingProtocol.owner_id == uid
                )
            )
            if record is None:
                raise BusinessError("Протокол не найден в вашем архиве.")
            tasks = list(
                s.scalars(
                    select(ProtocolTask)
                    .where(ProtocolTask.protocol_id == record.id)
                    .order_by(ProtocolTask.position)
                )
            )
            return {
                "id": record.id,
                "kind": record.kind,
                "payload": {
                    **record.payload,
                    "tasks": [
                        {
                            "action": task.action,
                            "assignee": task.assignee,
                            "due_date": task.due_date.isoformat() if task.due_date else None,
                            "due_text": task.due_text,
                        }
                        for task in tasks
                    ],
                },
            }
