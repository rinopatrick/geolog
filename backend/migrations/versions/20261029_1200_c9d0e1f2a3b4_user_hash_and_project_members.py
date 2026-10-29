"""user secret hashes and project memberships

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-29 12:00:00

Existing plaintext user tokens are replaced by PBKDF2 hashes. The plaintext
column is kept for upgrade compatibility but cleared, so a downgrade cannot
recover the original secret.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ITERATIONS = 240_000


def _hash_secret(secret: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, ITERATIONS)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def upgrade() -> None:
    op.add_column("users", sa.Column("token_hash", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, token FROM users WHERE token IS NOT NULL AND token != ''")
    ).fetchall()
    for user_id, token in rows:
        conn.execute(
            sa.text("UPDATE users SET token_hash = :token_hash, token = '' WHERE id = :user_id"),
            {"token_hash": _hash_secret(str(token)), "user_id": user_id},
        )

    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "subject", name="uq_project_member_subject"),
    )
    with op.batch_alter_table("project_members", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_project_members_id"), ["id"], unique=False)
        batch_op.create_index(batch_op.f("ix_project_members_project_id"), ["project_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_project_members_subject"), ["subject"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("project_members", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_project_members_subject"))
        batch_op.drop_index(batch_op.f("ix_project_members_project_id"))
        batch_op.drop_index(batch_op.f("ix_project_members_id"))
    op.drop_table("project_members")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("token_hash")
