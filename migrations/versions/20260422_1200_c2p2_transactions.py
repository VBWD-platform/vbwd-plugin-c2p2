"""Create c2p2_transactions table.

Revision ID: 20260422_1200_c2p2_tx
Revises: 20260420_1000_style_default
Create Date: 2026-04-22

Sprint 31 — 2C2P ASEAN plugin.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260422_1200_c2p2_tx"
down_revision = "20260420_1000_style_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "c2p2_transactions",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("invoice_no", sa.String(length=64), nullable=False, unique=True),
        sa.Column("merchant_id", sa.String(length=64), nullable=False),
        sa.Column("payment_token", sa.String(length=128), nullable=True),
        sa.Column("tran_ref", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("channel_code", sa.String(length=32), nullable=True),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="pending"
        ),
        sa.Column("last_resp_code", sa.String(length=8), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_c2p2_transactions_tran_ref",
        "c2p2_transactions",
        ["tran_ref"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_c2p2_transactions_tran_ref", table_name="c2p2_transactions")
    op.drop_table("c2p2_transactions")
