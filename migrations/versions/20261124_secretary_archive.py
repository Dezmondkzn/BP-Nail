"""Archive confirmed meeting protocols and their structured tasks."""

from alembic import op
import sqlalchemy as sa

revision = "20261124_secretary_archive"
down_revision = "20261110_telegram_identities"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_protocols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_meeting_protocols_owner_id", "meeting_protocols", ["owner_id"])
    op.create_table(
        "protocol_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("protocol_id", sa.Integer(), sa.ForeignKey("meeting_protocols.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("assignee", sa.String(200), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("due_text", sa.String(200), nullable=True),
        sa.UniqueConstraint("protocol_id", "position"),
    )
    op.create_index("ix_protocol_tasks_protocol_id", "protocol_tasks", ["protocol_id"])


def downgrade():
    op.drop_table("protocol_tasks")
    op.drop_table("meeting_protocols")
