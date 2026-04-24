"""2C2P services — domain mapping + webhook handling."""
from decimal import Decimal
from typing import Any, Dict, Optional

from vbwd.extensions import db

from plugins.c2p2.c2p2.models import C2P2Transaction


STATUS_BY_RESP_CODE_PREFIX = {
    "0000": "completed",
    "1": "processing",
    "2": "failed",
    "3": "cancelled",
}


def map_resp_code_to_status(resp_code: str) -> str:
    if not resp_code:
        return "failed"
    if resp_code in STATUS_BY_RESP_CODE_PREFIX:
        return STATUS_BY_RESP_CODE_PREFIX[resp_code]
    return STATUS_BY_RESP_CODE_PREFIX.get(resp_code[:1], "failed")


class C2P2Service:
    """Ingest 2C2P responses into the C2P2Transaction domain."""

    def __init__(self, session=None):
        self._session = session or db.session

    def record_token_issued(
        self,
        invoice_no: str,
        merchant_id: str,
        payment_token: str,
        amount: Decimal,
        currency: str,
        channel_code: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> C2P2Transaction:
        tx = self._get_or_create(invoice_no)
        tx.merchant_id = merchant_id
        tx.payment_token = payment_token
        tx.amount = amount
        tx.currency = currency
        tx.channel_code = channel_code
        tx.status = "pending"
        tx.extra_data = extra_data
        self._session.add(tx)
        self._session.commit()
        return tx

    def apply_inquiry(
        self, invoice_no: str, inquiry_payload: Dict[str, Any]
    ) -> C2P2Transaction:
        tx = self._get_or_create(invoice_no)
        resp_code = inquiry_payload.get("respCode", "")
        new_status = map_resp_code_to_status(resp_code)
        tran_ref = inquiry_payload.get("tranRef")

        if tx.status == new_status and tx.tran_ref == tran_ref:
            return tx

        tx.tran_ref = tran_ref
        tx.last_resp_code = resp_code
        tx.status = new_status
        self._session.commit()
        return tx

    def _get_or_create(self, invoice_no: str) -> C2P2Transaction:
        tx = (
            self._session.query(C2P2Transaction)
            .filter_by(invoice_no=invoice_no)
            .one_or_none()
        )
        if tx is None:
            tx = C2P2Transaction(
                invoice_no=invoice_no, amount=Decimal("0"), currency=""
            )
        return tx


class C2P2WebhookHandler:
    """Backend Notification handler — idempotent on invoiceNo + tranRef."""

    def __init__(self, service: Optional[C2P2Service] = None):
        self._service = service or C2P2Service()

    def handle(self, payload: Dict[str, Any]) -> C2P2Transaction:
        invoice_no = payload.get("invoiceNo")
        if not invoice_no:
            raise ValueError("missing invoiceNo in 2C2P backend notification")
        return self._service.apply_inquiry(invoice_no, payload)
