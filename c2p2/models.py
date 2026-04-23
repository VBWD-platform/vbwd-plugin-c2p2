"""2C2P payment transaction model."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Numeric, String

from vbwd.extensions import db


class C2P2Transaction(db.Model):
    """Mirror of a 2C2P payment for reconciliation + audit.

    One row per invoice; the payment token rotates if the user retries.
    """

    __tablename__ = "c2p2_transactions"

    id = Column(db.UUID, primary_key=True, server_default=db.text("gen_random_uuid()"))
    invoice_no = Column(String(64), nullable=False, unique=True, index=True)
    merchant_id = Column(String(64), nullable=False)
    payment_token = Column(String(128), nullable=True)
    tran_ref = Column(String(128), nullable=True, index=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    channel_code = Column(String(32), nullable=True)
    status = Column(String(24), nullable=False, default="pending")
    last_resp_code = Column(String(8), nullable=True)
    extra_data = Column(db.JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "invoice_no": self.invoice_no,
            "merchant_id": self.merchant_id,
            "payment_token": self.payment_token,
            "tran_ref": self.tran_ref,
            "amount": str(self.amount),
            "currency": self.currency,
            "channel_code": self.channel_code,
            "status": self.status,
            "last_resp_code": self.last_resp_code,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
