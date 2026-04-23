"""Unit tests for C2P2Service + C2P2WebhookHandler with MagicMock'd DB."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from plugins.c2p2.c2p2.services import (
    C2P2Service,
    C2P2WebhookHandler,
    map_resp_code_to_status,
)


class TestRespCodeMapping:
    @pytest.mark.parametrize(
        "resp_code,expected",
        [
            ("0000", "completed"),
            ("1000", "processing"),
            ("1234", "processing"),
            ("2001", "failed"),
            ("3000", "cancelled"),
            ("4999", "failed"),
            ("", "failed"),
        ],
    )
    def test_maps_expected_status(self, resp_code, expected):
        assert map_resp_code_to_status(resp_code) == expected


class TestC2P2Service:
    def test_record_token_issued_inserts_row(self):
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            None
        )
        service = C2P2Service(session=session)

        tx = service.record_token_issued(
            invoice_no="INV-1",
            merchant_id="JT01",
            payment_token="tok_abc",
            amount=Decimal("100"),
            currency="THB",
            channel_code="PROMPTPAY",
            extra_data={"foo": "bar"},
        )

        assert tx.invoice_no == "INV-1"
        assert tx.payment_token == "tok_abc"
        assert tx.status == "pending"
        session.add.assert_called_once()
        session.commit.assert_called()

    def test_apply_inquiry_updates_status(self):
        existing = MagicMock()
        existing.status = "pending"
        existing.tran_ref = None
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            existing
        )
        service = C2P2Service(session=session)

        service.apply_inquiry("INV-1", {"respCode": "0000", "tranRef": "TR-9"})

        assert existing.status == "completed"
        assert existing.tran_ref == "TR-9"
        assert existing.last_resp_code == "0000"
        session.commit.assert_called()

    def test_apply_inquiry_idempotent_on_same_state(self):
        existing = MagicMock()
        existing.status = "completed"
        existing.tran_ref = "TR-9"
        session = MagicMock()
        session.query.return_value.filter_by.return_value.one_or_none.return_value = (
            existing
        )
        service = C2P2Service(session=session)

        service.apply_inquiry("INV-1", {"respCode": "0000", "tranRef": "TR-9"})

        session.commit.assert_not_called()


class TestWebhookHandler:
    def test_raises_when_invoice_no_missing(self):
        handler = C2P2WebhookHandler(service=MagicMock())
        with pytest.raises(ValueError, match="invoiceNo"):
            handler.handle({"respCode": "0000"})

    def test_delegates_to_service(self):
        fake_service = MagicMock()
        handler = C2P2WebhookHandler(service=fake_service)
        handler.handle({"invoiceNo": "INV-1", "respCode": "0000", "tranRef": "TR-1"})
        fake_service.apply_inquiry.assert_called_once_with(
            "INV-1", {"invoiceNo": "INV-1", "respCode": "0000", "tranRef": "TR-1"}
        )
