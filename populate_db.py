"""Idempotent demo data for the 2C2P plugin.

Seeds one test transaction record so the admin-side transactions list has
something to display in the demo instance.
"""
from decimal import Decimal

from vbwd.extensions import db

from plugins.c2p2.c2p2.models import C2P2Transaction


def populate_db() -> None:
    existing = (
        db.session.query(C2P2Transaction)
        .filter_by(invoice_no="DEMO-C2P2-0001")
        .one_or_none()
    )
    if existing is not None:
        return

    db.session.add(
        C2P2Transaction(
            invoice_no="DEMO-C2P2-0001",
            merchant_id="JT01",
            payment_token="tok_demo_001",
            tran_ref="TR-DEMO-001",
            amount=Decimal("100.00"),
            currency="THB",
            channel_code="PROMPTPAY",
            status="completed",
            last_resp_code="0000",
            extra_data={"demo": True},
        )
    )
    db.session.commit()


if __name__ == "__main__":
    populate_db()
