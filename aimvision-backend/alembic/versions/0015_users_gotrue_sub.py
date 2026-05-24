"""Add users.gotrue_sub for ADR-0010 identity-provider linkage.

Revision ID: 0015_users_gotrue_sub
Revises: 0014_erasure
Create Date: 2026-05-24

Per ADR-0010, GoTrue is the source of truth for user identity; the
AIMVISION ``users`` row mirrors a GoTrue user by storing its UUID
``sub`` claim. Nullable until the cutover is complete (legacy users
still authenticate via the stub PBKDF2 path); the bulk-import script
populates this column for every existing user during migration.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0015_users_gotrue_sub"
down_revision = "0014_erasure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("gotrue_sub", sa.String(64), nullable=True),
    )
    # Unique among non-null values: one GoTrue user maps to one AIMVISION
    # user. Partial index avoids penalising the pre-cutover users (NULL).
    op.create_index(
        "ix_users_gotrue_sub",
        "users",
        ["gotrue_sub"],
        unique=True,
        postgresql_where=sa.text("gotrue_sub IS NOT NULL"),
        sqlite_where=sa.text("gotrue_sub IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_gotrue_sub", table_name="users")
    op.drop_column("users", "gotrue_sub")
