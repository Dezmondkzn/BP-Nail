import uuid
from datetime import timedelta
from sqlalchemy import select, update, or_, and_
from .models import Job, Version, now
from .documents import generate


class Worker:
    def __init__(self, sessions, storage, soffice="soffice", renderer=generate):
        self.sessions, self.storage, self.soffice, self.renderer = sessions, storage, soffice, renderer

    def once(self):
        token = uuid.uuid4().hex
        with self.sessions.begin() as s:
            eligible = or_(Job.state == "queued", and_(Job.state == "running", Job.lease_until < now()))
            job = s.scalar(
                select(Job).where(eligible).order_by(Job.id).with_for_update(skip_locked=True).limit(1)
            )
            if not job:
                return False
            changed = s.execute(
                update(Job)
                .where(Job.id == job.id, eligible)
                .values(
                    state="running",
                    token=token,
                    lease_until=now() + timedelta(minutes=5),
                    attempts=Job.attempts + 1,
                )
            )
            if not changed.rowcount:
                return False
            version = s.get(Version, job.version_id)
            view = {
                "id": version.quote_id,
                "version": version.number,
                "status": version.status,
                "payload": version.payload,
                "created_at": version.created_at.isoformat(),
            }
            job_id, attempts = job.id, job.attempts
        try:
            head = self.storage.get(view["payload"]["letterhead_key"])
            docx, pdf = self.renderer(head, view, self.soffice)
            prefix = f"quotes/{view['id']}/v{view['version']}/{token}"
            docx_key, pdf_key = prefix + ".docx", prefix + ".pdf"
            self.storage.put(
                docx_key, docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            self.storage.put(pdf_key, pdf, "application/pdf")
            with self.sessions.begin() as s:
                s.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.token == token)
                    .values(state="done", docx_key=docx_key, pdf_key=pdf_key, lease_until=None, error=None)
                )
        except Exception as exc:
            # Persist only the class, never URLs, keys or customer content from exception messages.
            with self.sessions.begin() as s:
                s.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.token == token)
                    .values(
                        state="queued" if attempts < 3 else "failed",
                        lease_until=None,
                        error=type(exc).__name__,
                    )
                )
        return True
