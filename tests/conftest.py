"""Shared fixtures for 2C2P plugin tests."""
import pytest

from vbwd.sdk.interface import SDKConfig


@pytest.fixture
def c2p2_config() -> dict:
    return {
        "test_merchant_id": "JT01",
        "test_secret_key": "secret-test-abc-123",
        "test_api_url": "https://sandbox-pgw.2c2p.com/payment/4.3",
        "sandbox": True,
        "enabled_methods": ["CC", "PROMPTPAY", "GCASH"],
        "default_currency": "THB",
        "allowed_currencies": ["THB", "SGD", "PHP", "USD"],
    }


@pytest.fixture
def sdk_config(c2p2_config) -> SDKConfig:
    return SDKConfig(
        api_key=c2p2_config["test_secret_key"],
        sandbox=c2p2_config["sandbox"],
    )


@pytest.fixture
def adapter(sdk_config, c2p2_config):
    from plugins.c2p2.c2p2.sdk_adapter import C2P2SDKAdapter

    return C2P2SDKAdapter(
        config=sdk_config,
        merchant_id=c2p2_config["test_merchant_id"],
        api_url=c2p2_config["test_api_url"],
    )
