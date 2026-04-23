# 2C2P Plugin (Backend)

2C2P Payment Gateway v4 adapter — cards + regional ASEAN wallets via a
single PSP: PromptPay, PayNow, DuitNow, QRIS, GCash, MoMo, ShopeePay,
TrueMoney, Alipay, WeChat Pay, FPX.

## Purpose

Implements `PaymentProviderPlugin` for 2C2P PGW v4. Uses JWS-signed
JSON (HS256) over HTTPS per 2C2P developer docs. Handles token
issuance, inquiry, refund, void, and Backend Notification webhooks.

## Configuration (`plugins/config.json`)

```json
{
  "c2p2": {
    "sandbox": true,
    "test_merchant_id": "JT01",
    "test_secret_key": "…",
    "enabled_methods": ["CC", "PROMPTPAY", "GCASH"],
    "default_currency": "THB",
    "allowed_currencies": ["THB", "SGD", "PHP"]
  }
}
```

## API Routes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/plugins/c2p2/payment-tokens` | Bearer | Issue a paymentToken for an invoice |
| GET | `/api/v1/plugins/c2p2/payments/:invoice/status` | Bearer | Query latest status from 2C2P |
| POST | `/api/v1/plugins/c2p2/backend-notifications` | JWS signature | 2C2P Backend Notification receiver |
| POST | `/api/v1/plugins/c2p2/payments/:invoice/refund` | Admin | Refund (full or partial) |

## Events

Emits `PaymentCapturedEvent` when Backend Notification reports
`respCode=0000`. Emits `PaymentFailedEvent` on non-zero terminal codes.

## Database

Owns the `c2p2_transactions` table. One row per invoice; updates on
inquiry/webhook.

## Frontend bundles

- User: [`vbwd-fe-user-plugin-2c2p`](https://github.com/VBWD-platform/vbwd-fe-user-plugin-2c2p)
- Admin: [`vbwd-fe-admin-plugin-2c2p`](https://github.com/VBWD-platform/vbwd-fe-admin-plugin-2c2p)

## Testing

```bash
docker compose run --rm test python -m pytest plugins/c2p2/tests/ -v
```

## Core requirements

All work in this plugin follows
`docs/dev_log/20260422/sprints/_engineering-requirements.md`:
TDD-first, DevOps-first, SOLID (with Liskov explicitly enforced on
`PaymentProviderPlugin` subclasses), DRY, DI, clean code, no
over-engineering, drop deprecated. Gated by
`bin/pre-commit-check.sh --full` in CI.

---

## Related

**Core:** [vbwd-backend](https://github.com/VBWD-platform/vbwd-backend)
