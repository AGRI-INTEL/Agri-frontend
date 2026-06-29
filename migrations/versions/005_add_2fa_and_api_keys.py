"""Add 2FA fields to users and create api_keys table

Revision ID: 005
Revises: 004_add_registration_fields
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004_add_registration_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    # ── 2FA columns on users (idempotent: skip if already exist) ─────
    if "totp_secret" not in existing_columns:
        op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    if "totp_enabled" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("totp_enabled", sa.Boolean(), server_default="false", nullable=False),
        )
    if "totp_backup_codes" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("totp_backup_codes", postgresql.JSONB(), nullable=True),
        )

    # ── api_keys table (idempotent: skip if already exists) ───────────
    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("key_prefix", sa.String(20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
        op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_table("api_keys")
    op.drop_column("users", "totp_backup_codes")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
