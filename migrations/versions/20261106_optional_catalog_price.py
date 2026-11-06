"""Catalog is nomenclature; prices are entered by managers."""

from alembic import op
import sqlalchemy as sa

revision = "20261106_manual_price"
down_revision = "8000e9eec892"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("products") as batch:
        batch.alter_column("price", existing_type=sa.Numeric(18, 2), nullable=True)
        batch.alter_column("price_date", existing_type=sa.String(10), nullable=True)
        batch.alter_column("valid_until", existing_type=sa.String(10), nullable=True)


def downgrade():
    raise RuntimeError("Cannot restore mandatory catalog prices without user-supplied prices")
