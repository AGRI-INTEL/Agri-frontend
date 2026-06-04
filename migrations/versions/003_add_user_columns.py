"""Add missing users columns (cover_url, created_by, updated_by)

Revision ID: 003_add_user_columns
Revises: 002_community_files
Create Date: 2026-06-04 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "003_add_user_columns"
down_revision = "002_community_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns that exist in the User model but were not created by 001_initial."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    if "cover_url" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("cover_url", sa.String(length=500), nullable=True),
        )

    if "created_by" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if "updated_by" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )


def downgrade() -> None:
    """Remove the columns added in this migration."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    if "updated_by" in existing_columns:
        op.drop_column("users", "updated_by")
    if "created_by" in existing_columns:
        op.drop_column("users", "created_by")
    if "cover_url" in existing_columns:
        op.drop_column("users", "cover_url")
