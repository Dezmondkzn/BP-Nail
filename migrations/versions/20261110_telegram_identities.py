"""Remember observed Telegram usernames independently of granted access."""

from alembic import op
import sqlalchemy as sa

revision = "20261110_telegram_identities"
down_revision = "20261106_manual_price"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "telegram_identities",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(32), nullable=True, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("seen_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("telegram_identities")
