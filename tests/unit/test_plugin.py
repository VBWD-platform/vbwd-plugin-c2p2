"""Plugin-class unit tests — metadata + Liskov: override initialize calls super."""
from vbwd.plugins.base import PluginStatus

from plugins.c2p2 import C2P2Plugin, DEFAULT_CONFIG


class TestC2P2Plugin:
    def test_metadata(self):
        plugin = C2P2Plugin()
        meta = plugin.metadata
        assert meta.name == "c2p2"
        assert meta.version == "26.6.1"

    def test_initialize_merges_defaults(self):
        plugin = C2P2Plugin()
        plugin.initialize({"test_merchant_id": "JT01"})

        assert plugin.status == PluginStatus.INITIALIZED
        assert plugin._config["test_merchant_id"] == "JT01"
        assert plugin._config["default_currency"] == DEFAULT_CONFIG["default_currency"]

    def test_url_prefix(self):
        plugin = C2P2Plugin()
        assert plugin.get_url_prefix() == "/api/v1/plugins/c2p2"
