"""2C2P SDK adapter implementing ISDKAdapter.

2C2P Payment Gateway v4 uses JWT-signed request/response payloads.
Reference: https://developer.2c2p.com/docs/api-payment-token
"""
import base64
import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any, Dict, Optional

import requests

from vbwd.sdk.base import BaseSDKAdapter
from vbwd.sdk.interface import SDKConfig, SDKResponse


class C2P2SDKAdapter(BaseSDKAdapter):
    """2C2P Payment Gateway v4 adapter.

    Liskov: honours every postcondition of BaseSDKAdapter — on success a
    SDKResponse with `success=True` and `data` populated; on failure
    `success=False` with `error` set.
    """

    def __init__(
        self,
        config: SDKConfig,
        merchant_id: str,
        api_url: str,
        idempotency_service=None,
    ):
        super().__init__(config, idempotency_service)
        self._merchant_id = merchant_id
        self._api_url = api_url.rstrip("/")
        self._secret_key = config.api_key

    @property
    def provider_name(self) -> str:
        return "c2p2"

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        metadata: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        """ISDKAdapter contract: 2C2P's equivalent is a paymentToken."""
        invoice_no = metadata.get("invoice_no") or metadata.get("invoiceNo") or ""
        user_id = metadata.get("user_id") or metadata.get("userId") or ""
        return self.create_payment_token(
            amount=amount,
            currency=currency,
            invoice_no=invoice_no,
            user_id=user_id,
            metadata=metadata,
            description=metadata.get("description", "Payment"),
            payment_channel=metadata.get("payment_channel"),
        )

    def capture_payment(
        self,
        payment_intent_id: str,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        """2C2P auto-captures on method confirm; inquiry is the status check."""
        return self.payment_inquiry(invoice_no=payment_intent_id)

    def release_authorization(self, payment_intent_id: str) -> SDKResponse:
        return self.void_payment(invoice_no=payment_intent_id)

    def get_payment_status(self, payment_intent_id: str) -> SDKResponse:
        return self.payment_inquiry(invoice_no=payment_intent_id)

    def create_payment_token(
        self,
        amount: Decimal,
        currency: str,
        invoice_no: str,
        user_id: str,
        metadata: Dict[str, Any],
        description: str = "Payment",
        payment_channel: Optional[str] = None,
    ) -> SDKResponse:
        """Issue a paymentToken for the hosted-redirect or inline flow.

        Returns `{ paymentToken, webPaymentUrl, respCode }` on success.
        """
        payload: Dict[str, Any] = {
            "merchantID": self._merchant_id,
            "invoiceNo": invoice_no,
            "description": description,
            "amount": float(amount),
            "currencyCode": currency,
            "userDefined1": user_id,
        }
        if metadata.get("return_url"):
            payload["frontendReturnUrl"] = metadata["return_url"]
        if metadata.get("backend_url"):
            payload["backendReturnUrl"] = metadata["backend_url"]
        if payment_channel:
            payload["paymentChannel"] = [payment_channel]

        return self._post_jwt("/paymentToken", payload)

    def payment_inquiry(self, invoice_no: str) -> SDKResponse:
        """Query status by invoiceNo. Returns `{ respCode, tranRef, ... }`."""
        payload = {"merchantID": self._merchant_id, "invoiceNo": invoice_no}
        return self._post_jwt("/paymentInquiry", payload)

    def refund_payment(
        self,
        payment_intent_id: str,
        amount: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None,
    ) -> SDKResponse:
        """Refund (full when amount is None, partial otherwise).

        `payment_intent_id` is the 2C2P invoiceNo — consistent with how 2C2P
        keys refunds.
        """
        payload: Dict[str, Any] = {
            "merchantID": self._merchant_id,
            "invoiceNo": payment_intent_id,
        }
        if amount is not None:
            payload["amount"] = float(amount)
        return self._post_jwt("/payment/refund", payload)

    def void_payment(self, invoice_no: str) -> SDKResponse:
        """Void/release an authorized hold."""
        payload = {
            "merchantID": self._merchant_id,
            "invoiceNo": invoice_no,
            "processType": "V",
        }
        return self._post_jwt("/payment/cancel", payload)

    def verify_backend_notification(
        self, payload: bytes, signature: str
    ) -> bool:
        """Verify the 2C2P Backend Notification signature.

        The BN arrives as a form-urlencoded body where the `paymentResponse`
        field is a JWT signed with the merchant's secret key. Verification
        just re-runs the JWS HMAC over header.payload and compares.
        """
        if not signature or "." not in signature:
            return False
        parts = signature.split(".")
        if len(parts) != 3:
            return False
        header_b64, payload_b64, received_sig = parts
        expected_sig = self._hs256(f"{header_b64}.{payload_b64}")
        return hmac.compare_digest(expected_sig, received_sig)

    # ── JWT-signed request helpers ─────────────────────────────────────

    def _post_jwt(self, path: str, payload: Dict[str, Any]) -> SDKResponse:
        def _call() -> SDKResponse:
            signed = self._sign_jws(payload)
            url = f"{self._api_url}{path}"
            try:
                resp = requests.post(
                    url,
                    data=signed,
                    headers={"Content-Type": "text/plain"},
                    timeout=30,
                )
            except requests.RequestException as exc:
                return SDKResponse(
                    success=False, error=f"network: {exc}"
                )

            if resp.status_code >= 500:
                return SDKResponse(
                    success=False,
                    error=(
                        f"2C2P returned {resp.status_code}: {resp.text[:200]}"
                    ),
                )

            decoded = self._decode_jws(resp.text)
            if decoded is None:
                return SDKResponse(
                    success=False,
                    error="invalid JWS from 2C2P",
                )

            resp_code = decoded.get("respCode", "")
            if resp_code != "0000" and not resp_code.startswith("1"):
                return SDKResponse(
                    success=False,
                    data=decoded,
                    error=(
                        decoded.get("respDesc")
                        or f"2C2P declined with respCode={resp_code}"
                    ),
                )
            return SDKResponse(success=True, data=decoded)

        return _call()

    def _sign_jws(self, payload: Dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url(
            json.dumps(payload, separators=(",", ":")).encode()
        )
        signing_input = f"{header_b64}.{payload_b64}"
        signature = self._hs256(signing_input)
        return f"{signing_input}.{signature}"

    def _decode_jws(self, token: str) -> Optional[Dict[str, Any]]:
        if not token or "." not in token:
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, received_sig = parts
        expected_sig = self._hs256(f"{header_b64}.{payload_b64}")
        if not hmac.compare_digest(expected_sig, received_sig):
            return None
        try:
            return json.loads(_b64url_decode(payload_b64))
        except (ValueError, json.JSONDecodeError):
            return None

    def _hs256(self, signing_input: str) -> str:
        digest = hmac.new(
            self._secret_key.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        return _b64url(digest)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data = data + ("=" * padding)
    return base64.urlsafe_b64decode(data.encode("ascii"))
