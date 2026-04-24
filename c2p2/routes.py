"""2C2P plugin API routes."""
import logging
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from vbwd.middleware.auth import require_auth

from plugins.c2p2.c2p2.services import C2P2Service, C2P2WebhookHandler

logger = logging.getLogger(__name__)

c2p2_plugin_bp = Blueprint("c2p2_plugin", __name__)


def _get_plugin():
    manager = current_app.plugin_manager
    plugin = manager.get_plugin("c2p2")
    if plugin is None:
        raise RuntimeError("c2p2 plugin not enabled")
    return plugin


@c2p2_plugin_bp.route("/payment-tokens", methods=["POST"])
@require_auth
def create_payment_token():
    """Issue a 2C2P payment token for an invoice.

    Body: { invoice_no, amount, currency, description?, return_url?,
            payment_channel? }
    """
    body = request.get_json(silent=True) or {}
    required = ("invoice_no", "amount", "currency")
    missing = [f for f in required if not body.get(f)]
    if missing:
        return (
            jsonify({"error": "missing fields", "fields": missing}),
            400,
        )

    try:
        amount = Decimal(str(body["amount"]))
    except (ValueError, ArithmeticError):
        return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.create_payment_token(
        amount=amount,
        currency=body["currency"],
        invoice_no=body["invoice_no"],
        user_id=str(getattr(request, "user_id", "")),
        metadata={
            "return_url": body.get("return_url"),
            "backend_url": body.get("backend_url"),
        },
        description=body.get("description", "Payment"),
        payment_channel=body.get("payment_channel"),
    )
    if not response.success:
        return (
            jsonify({"error": response.error or "2C2P error"}),
            502,
        )

    service = C2P2Service()
    service.record_token_issued(
        invoice_no=body["invoice_no"],
        merchant_id=adapter._merchant_id,
        payment_token=response.data.get("paymentToken", ""),
        amount=amount,
        currency=body["currency"],
        channel_code=body.get("payment_channel"),
        extra_data=response.data,
    )

    return (
        jsonify(
            {
                "payment_token": response.data.get("paymentToken"),
                "web_payment_url": response.data.get("webPaymentUrl"),
            }
        ),
        201,
    )


@c2p2_plugin_bp.route("/payments/<invoice_no>/status", methods=["GET"])
@require_auth
def get_payment_status(invoice_no: str):
    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.payment_inquiry(invoice_no=invoice_no)
    if not response.success:
        return (
            jsonify({"error": response.error or "2C2P error"}),
            502,
        )
    service = C2P2Service()
    tx = service.apply_inquiry(invoice_no, response.data)
    return jsonify(tx.to_dict()), 200


@c2p2_plugin_bp.route("/backend-notifications", methods=["POST"])
def backend_notification():
    """2C2P Backend Notification (server-to-server webhook)."""
    token = request.form.get("paymentResponse") or request.data.decode(
        "utf-8", errors="ignore"
    )
    if not token:
        return jsonify({"error": "empty payload"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    payload = adapter._decode_jws(token)
    if payload is None:
        return jsonify({"error": "invalid signature"}), 401

    handler = C2P2WebhookHandler()
    handler.handle(payload)
    return "", 204


@c2p2_plugin_bp.route("/payments/<invoice_no>/refund", methods=["POST"])
@require_auth
def refund_payment(invoice_no: str):
    body = request.get_json(silent=True) or {}
    amount = body.get("amount")
    if amount is not None:
        try:
            amount = Decimal(str(amount))
        except (ValueError, ArithmeticError):
            return jsonify({"error": "invalid amount"}), 400

    plugin = _get_plugin()
    adapter = plugin._get_adapter()
    response = adapter.refund_payment(payment_intent_id=invoice_no, amount=amount)
    if not response.success:
        return (
            jsonify({"error": response.error or "2C2P error"}),
            502,
        )
    return jsonify({"tran_ref": response.data.get("tranRef")}), 200
