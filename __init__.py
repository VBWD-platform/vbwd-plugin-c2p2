"""2C2P Payment Gateway plugin — ASEAN cards, QR, wallets via PGW v4."""
from typing import Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from uuid import UUID

from vbwd.plugins.base import PluginMetadata
from vbwd.plugins.payment_provider import (
    PaymentProviderPlugin,
    PaymentResult,
    PaymentStatus,
)

if TYPE_CHECKING:
    from flask import Blueprint


DEFAULT_CONFIG = {
    "sandbox": True,
    "test_merchant_id": "",
    "test_secret_key": "",
    "test_api_url": "https://sandbox-pgw.2c2p.com/payment/4.3",
    "live_merchant_id": "",
    "live_secret_key": "",
    "live_api_url": "https://pgw.2c2p.com/payment/4.3",
    "enabled_methods": [
        "CC",
        "PROMPTPAY",
        "PAYNOW",
        "DUITNOW",
        "QRIS",
        "GCASH",
        "MOMO",
        "SHOPEEPAY",
        "TRUEMONEY",
        "ALIPAY",
        "WECHATPAY",
        "FPX",
    ],
    "default_currency": "THB",
    "allowed_currencies": [
        "THB",
        "SGD",
        "MYR",
        "PHP",
        "VND",
        "IDR",
        "HKD",
        "TWD",
        "USD",
    ],
}


class C2P2Plugin(PaymentProviderPlugin):
    """2C2P Payment Gateway v4 — cards + QR + regional wallets.

    Class MUST be defined in __init__.py (not re-exported) due to
    discovery check obj.__module__ != full_module in manager.py.
    """

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="c2p2",
            version="1.0.0",
            author="VBWD Team",
            description=(
                "2C2P Payment Gateway v4 — ASEAN cards, QR, and regional "
                "wallets (PromptPay, PayNow, DuitNow, QRIS, GCash, MoMo, "
                "ShopeePay, TrueMoney, Alipay, WeChat Pay, FPX)"
            ),
            dependencies=[],
        )

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        merged = {**DEFAULT_CONFIG}
        if config:
            merged.update(config)
        super().initialize(merged)

    def get_blueprint(self) -> Optional["Blueprint"]:
        from plugins.c2p2.c2p2.routes import c2p2_plugin_bp

        return c2p2_plugin_bp

    def get_url_prefix(self) -> Optional[str]:
        return "/api/v1/plugins/c2p2"

    @property
    def admin_permissions(self):
        return [
            {
                "key": "payments.configure",
                "label": "Payment provider settings",
                "group": "Payments",
            },
        ]

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def _get_adapter(self):
        from flask import current_app
        from plugins.c2p2.c2p2.sdk_adapter import C2P2SDKAdapter
        from vbwd.sdk.interface import SDKConfig

        config_store = current_app.config_store
        config = config_store.get_config("c2p2")
        prefix = "test_" if config.get("sandbox", True) else "live_"
        api_key = config.get(f"{prefix}secret_key") or config.get(
            "secret_key", ""
        )
        return C2P2SDKAdapter(
            SDKConfig(api_key=api_key, sandbox=config.get("sandbox", True)),
            merchant_id=config.get(f"{prefix}merchant_id", ""),
            api_url=config.get(
                f"{prefix}api_url", DEFAULT_CONFIG[f"{prefix}api_url"]
            ),
        )

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str,
        subscription_id: UUID,
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None,
        capture: bool = True,
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.create_payment_token(
            amount=amount,
            currency=currency,
            invoice_no=str(subscription_id),
            user_id=str(user_id),
            metadata=metadata or {},
        )
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=response.data.get("paymentToken"),
            status=PaymentStatus.PENDING,
            metadata={
                "web_payment_url": response.data.get("webPaymentUrl"),
                "payment_token": response.data.get("paymentToken"),
            },
        )

    def capture_payment(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.payment_inquiry(invoice_no=payment_id)
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        status = _map_respcode_to_status(response.data.get("respCode", ""))
        return PaymentResult(
            success=status == PaymentStatus.COMPLETED,
            transaction_id=response.data.get("tranRef"),
            status=status,
        )

    def release_authorization(self, payment_id: str) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.void_payment(invoice_no=payment_id)
        return _payment_result_from_response(response)

    def process_payment(
        self, payment_intent_id: str, payment_method: str
    ) -> PaymentResult:
        return self.capture_payment(payment_intent_id)

    def refund_payment(
        self, transaction_id: str, amount: Optional[Decimal] = None
    ) -> PaymentResult:
        adapter = self._get_adapter()
        response = adapter.refund_payment(
            payment_intent_id=transaction_id, amount=amount
        )
        if not response.success:
            return PaymentResult(
                success=False,
                error_message=response.error,
                status=PaymentStatus.FAILED,
            )
        return PaymentResult(
            success=True,
            transaction_id=response.data.get("tranRef"),
            status=PaymentStatus.REFUNDED,
        )

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        adapter = self._get_adapter()
        return adapter.verify_backend_notification(payload, signature)

    def handle_webhook(self, payload: Dict[str, Any]) -> None:
        from plugins.c2p2.c2p2.services import C2P2WebhookHandler

        handler = C2P2WebhookHandler()
        handler.handle(payload)


def _map_respcode_to_status(resp_code: str) -> PaymentStatus:
    """Map 2C2P response code to PaymentStatus.

    Per 2C2P PGW v4 response code registry:
    - "0000" = success
    - "1xxx" = processing/pending
    - "2xxx" = declined
    - "3xxx" = cancelled by user
    - "4xxx"+ = system failure
    """
    if resp_code == "0000":
        return PaymentStatus.COMPLETED
    if resp_code.startswith("1"):
        return PaymentStatus.PROCESSING
    if resp_code.startswith("3"):
        return PaymentStatus.CANCELLED
    return PaymentStatus.FAILED


def _payment_result_from_response(response) -> PaymentResult:
    if not response.success:
        return PaymentResult(
            success=False,
            error_message=response.error,
            status=PaymentStatus.FAILED,
        )
    return PaymentResult(
        success=True,
        transaction_id=response.data.get("tranRef"),
        status=_map_respcode_to_status(response.data.get("respCode", "")),
    )
