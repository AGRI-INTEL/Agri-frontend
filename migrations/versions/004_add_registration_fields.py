"""Add sector, profile_role, newsletter to users table

Revision ID: 004_add_registration_fields
Revises: 003_add_user_columns
Create Date: 2026-06-21 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "004_add_registration_fields"
down_revision = "003_add_user_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    if "sector" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("sector", sa.String(length=50), nullable=True),
        )

    if "profile_role" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("profile_role", sa.String(length=50), nullable=True),
        )

    if "newsletter" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("newsletter", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("users")}

    if "newsletter" in existing_columns:
        op.drop_column("users", "newsletter")
    if "profile_role" in existing_columns:
        op.drop_column("users", "profile_role")
    if "sector" in existing_columns:
        op.drop_column("users", "sector")
