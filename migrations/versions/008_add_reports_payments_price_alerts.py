"""Crée les tables reports, subscription_plans, user_subscriptions, invoices, price_alerts

Cette migration remplace l'ancienne version basée sur Base.metadata.create_all
par des op.create_table() explicites — plus robustes, sans dépendance aux imports
d'application (évite les timeouts et crash-loops).

Revision ID: 008_add_reports_payments_price_alerts
Revises: 007_add_performance_indexes
"""

revision = '008_add_reports_payments_price_alerts'
down_revision = '007_add_performance_indexes'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    # ── reports ───────────────────────────────────────────────────────────
    if "reports" not in existing:
        op.create_table(
            "reports",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("report_type", sa.String(50), nullable=False),
            sa.Column("format", sa.String(10), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
            sa.Column("file_path", sa.String(500), nullable=True),
            sa.Column("file_size", sa.String(50), nullable=True),
            sa.Column("parameters", postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index("ix_reports_user_id", "reports", ["user_id"])
        op.create_index("ix_reports_type", "reports", ["report_type"])
        op.create_index("ix_reports_created_at", "reports", ["created_at"])

    # ── subscription_plans ────────────────────────────────────────────────
    if "subscription_plans" not in existing:
        op.create_table(
            "subscription_plans",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False, unique=True),
            sa.Column("slug", sa.String(50), nullable=False, unique=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("price_monthly", sa.Float, nullable=False),
            sa.Column("price_yearly", sa.Float, nullable=True),
            sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
            sa.Column("features", postgresql.JSONB, nullable=True),
            sa.Column("limits", postgresql.JSONB, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )

    # ── user_subscriptions ────────────────────────────────────────────────
    if "user_subscriptions" not in existing:
        op.create_table(
            "user_subscriptions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subscription_plans.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("billing_cycle", sa.String(10), nullable=False, server_default="monthly"),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("payment_method", sa.String(50), nullable=True),
            sa.Column("auto_renew", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("metadata", postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
        op.create_index("ix_user_subscriptions_plan_id", "user_subscriptions", ["plan_id"])
        op.create_index("ix_user_subscriptions_status", "user_subscriptions", ["status"])

    # ── invoices ──────────────────────────────────────────────────────────
    if "invoices" not in existing:
        op.create_table(
            "invoices",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_subscriptions.id"), nullable=True),
            sa.Column("amount", sa.Float, nullable=False),
            sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("payment_method", sa.String(50), nullable=True),
            sa.Column("payment_reference", sa.String(255), nullable=True),
            sa.Column("invoice_url", sa.String(500), nullable=True),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", postgresql.JSONB, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
        op.create_index("ix_invoices_status", "invoices", ["status"])
        op.create_index("ix_invoices_created_at", "invoices", ["created_at"])

    # ── price_alerts ──────────────────────────────────────────────────────
    if "price_alerts" not in existing:
        op.create_table(
            "price_alerts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("crop", sa.String(100), nullable=False),
            sa.Column("market", sa.String(200), nullable=False),
            sa.Column("condition", sa.String(10), nullable=False),
            sa.Column("threshold", sa.Float, nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="FCFA"),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index("ix_price_alerts_user_id", "price_alerts", ["user_id"])
        op.create_index("ix_price_alerts_crop", "price_alerts", ["crop"])
        op.create_index("ix_price_alerts_active", "price_alerts", ["is_active"])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing = inspector.get_table_names()

    for table in ("price_alerts", "invoices", "user_subscriptions", "subscription_plans", "reports"):
        if table in existing:
            op.drop_table(table)
