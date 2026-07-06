"""Increase key_hash column to 128 chars for bcrypt

Revision ID: 009
Revises: 008_add_reports_payments_price_alerts
Create Date: 2026-07-05

"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008_add_reports_payments_price_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("api_keys"):
        columns = {c["name"]: c for c in inspector.get_columns("api_keys")}
        col = columns.get("key_hash")
        if col and col.get("type") and hasattr(col["type"], "length") and col["type"].length == 64:
            op.alter_column("api_keys", "key_hash", type_=sa.String(128))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("api_keys"):
        columns = {c["name"]: c for c in inspector.get_columns("api_keys")}
        col = columns.get("key_hash")
        if col and col.get("type") and hasattr(col["type"], "length") and col["type"].length == 128:
            op.alter_column("api_keys", "key_hash", type_=sa.String(64))
