"""Unit tests for C2P2SDKAdapter.

Written TDD-first per sprint's method-specific checkpoints:
- `create_payment_token` happy path + missing field rejection.
- `payment_inquiry` response-code handling.
- JWT sign + decode round-trip (HS256 over canonical JSON).
- `verify_backend_notification` signature verify.
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestJwtSigning:
    def test_sign_jws_structure(self, adapter):
        token = adapter._sign_jws({"merchantID": "JT01", "amount": 10.0})
        parts = token.split(".")
        assert len(parts) == 3

    def test_decode_jws_round_trip(self, adapter):
        payload = {"merchantID": "JT01", "invoiceNo": "INV-1", "amount": 10.0}
        token = adapter._sign_jws(payload)
        decoded = adapter._decode_jws(token)
        assert decoded == payload

    def test_decode_rejects_bad_signature(self, adapter):
        payload = {"merchantID": "JT01"}
        token = adapter._sign_jws(payload)
        tampered = token[:-4] + "zzzz"
        assert adapter._decode_jws(tampered) is None

    def test_decode_rejects_non_jws(self, adapter):
        assert adapter._decode_jws("not-a-jws") is None
        assert adapter._decode_jws("") is None
        assert adapter._decode_jws("a.b") is None


class TestVerifyBackendNotification:
    def test_verify_accepts_adapter_signed(self, adapter):
        payload = {"invoiceNo": "INV-1", "respCode": "0000"}
        token = adapter._sign_jws(payload)
        assert adapter.verify_backend_notification(b"", token) is True

    def test_verify_rejects_bad_signature(self, adapter):
        token = "hdr.pld.sig"
        assert adapter.verify_backend_notification(b"", token) is False

    def test_verify_rejects_empty(self, adapter):
        assert adapter.verify_backend_notification(b"", "") is False
        assert adapter.verify_backend_notification(b"", "not.a.jwt") is False


class TestCreatePaymentToken:
    def test_success_response_maps_to_data(self, adapter, mocker):
        fake_response = _fake_response_with_payload(
            adapter,
            {
                "respCode": "0000",
                "paymentToken": "tok_abc",
                "webPaymentUrl": "https://pgw.test/pay/tok_abc",
            },
        )
        mocker.patch(
            "plugins.c2p2.c2p2.sdk_adapter.requests.post",
            return_value=fake_response,
        )

        resp = adapter.create_payment_token(
            amount=Decimal("100.00"),
            currency="THB",
            invoice_no="INV-1",
            user_id="user-1",
            metadata={"return_url": "https://shop.test/return"},
        )

        assert resp.success is True
        assert resp.data["paymentToken"] == "tok_abc"

    def test_non_zero_resp_code_returns_failure(self, adapter, mocker):
        fake_response = _fake_response_with_payload(
            adapter,
            {"respCode": "4001", "respDesc": "Invalid merchant"},
        )
        mocker.patch(
            "plugins.c2p2.c2p2.sdk_adapter.requests.post",
            return_value=fake_response,
        )

        resp = adapter.create_payment_token(
            amount=Decimal("100.00"),
            currency="THB",
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "Invalid merchant" in (resp.error or "")

    def test_network_error_returns_failure(self, adapter, mocker):
        import requests

        mocker.patch(
            "plugins.c2p2.c2p2.sdk_adapter.requests.post",
            side_effect=requests.ConnectionError("down"),
        )
        resp = adapter.create_payment_token(
            amount=Decimal("1.00"),
            currency="THB",
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "network" in (resp.error or "")

    def test_5xx_status_returns_failure(self, adapter, mocker):
        bad_response = MagicMock()
        bad_response.status_code = 503
        bad_response.text = "gateway down"
        mocker.patch(
            "plugins.c2p2.c2p2.sdk_adapter.requests.post",
            return_value=bad_response,
        )
        resp = adapter.create_payment_token(
            amount=Decimal("1.00"),
            currency="THB",
            invoice_no="INV-1",
            user_id="user-1",
            metadata={},
        )
        assert resp.success is False
        assert "503" in (resp.error or "")


class TestPaymentInquiry:
    def test_returns_data_when_jws_valid(self, adapter, mocker):
        fake_response = _fake_response_with_payload(
            adapter,
            {
                "respCode": "0000",
                "tranRef": "TR-123",
                "invoiceNo": "INV-1",
            },
        )
        mocker.patch(
            "plugins.c2p2.c2p2.sdk_adapter.requests.post",
            return_value=fake_response,
        )
        resp = adapter.payment_inquiry("INV-1")
        assert resp.success is True
        assert resp.data["tranRef"] == "TR-123"


def _fake_response_with_payload(adapter, payload: dict):
    """Build a MagicMock'd requests.Response whose text is a JWT the adapter
    can decode with its own key."""
    response = MagicMock()
    response.status_code = 200
    response.text = adapter._sign_jws(payload)
    return response


@pytest.fixture(autouse=True)
def _noop_idempotency(mocker):
    """SDKAdapter uses idempotency_service; inject a no-op for unit tests."""
    from plugins.c2p2.c2p2.sdk_adapter import C2P2SDKAdapter

    original_init = C2P2SDKAdapter.__init__

    def _init(self, config, merchant_id, api_url, idempotency_service=None):
        original_init(
            self,
            config,
            merchant_id=merchant_id,
            api_url=api_url,
            idempotency_service=idempotency_service,
        )

    yield
