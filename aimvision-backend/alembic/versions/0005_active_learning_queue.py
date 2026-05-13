"""Active learning queue table — Sprint 6 EPIC 6.5.

Revision ID: 0005_active_learning_queue
Revises: 0004_federation_v2
Create Date: 2026-05-13

Adds `active_learning_items` for queuing low-confidence ML outputs that
need expert labelling. Tenant-scoped with the same RLS pattern as the
other tenant tables.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_active_learning_queue"
down_revision = "0004_federation_v2"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    al_signal = sa.Enum(
        "low_confidence",
        "ood_drift",
        "disagreement_with_classical",
        "rare_class",
        "manual_flag",
        name="al_uncertainty_signal",
    )
    al_status = sa.Enum(
        "pending",
        "claimed",
        "labelled",
        "discarded",
        name="al_status",
    )
    if _is_postgres():
        al_signal.create(op.get_bind(), checkfirst=True)
        al_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "active_learning_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "shot_id",
            sa.String(64),
            sa.ForeignKey("shots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("prediction", sa.JSON, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("uncertainty_signal", al_signal, nullable=False),
        sa.Column("status", al_status, nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "annotator_user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels", sa.JSON, nullable=True),
        sa.Column("annotator_note", sa.String(2048), nullable=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_active_learning_items_tenant_id", "active_learning_items", ["tenant_id"])
    op.create_index("ix_active_learning_items_session_id", "active_learning_items", ["session_id"])
    op.create_index("ix_active_learning_items_shot_id", "active_learning_items", ["shot_id"])
    op.create_index(
        "ix_active_learning_items_status_priority",
        "active_learning_items",
        ["status", "priority"],
    )

    if _is_postgres():
        op.execute("ALTER TABLE active_learning_items ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE active_learning_items FORCE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY active_learning_items_tenant_isolation
            ON active_learning_items
            USING (tenant_id = current_setting('aimvision.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('aimvision.tenant_id', true))
            """
        )


def downgrade() -> None:
    if _is_postgres():
        op.execute(
            "DROP POLICY IF EXISTS active_learning_items_tenant_isolation ON active_learning_items"
        )

    op.drop_index("ix_active_learning_items_status_priority", table_name="active_learning_items")
    op.drop_index("ix_active_learning_items_shot_id", table_name="active_learning_items")
    op.drop_index("ix_active_learning_items_session_id", table_name="active_learning_items")
    op.drop_index("ix_active_learning_items_tenant_id", table_name="active_learning_items")
    op.drop_table("active_learning_items")

    if _is_postgres():
        op.execute("DROP TYPE IF EXISTS al_status")
        op.execute("DROP TYPE IF EXISTS al_uncertainty_signal")
