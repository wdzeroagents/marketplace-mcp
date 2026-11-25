"""The capability manifest is the stable adapter-discovery contract."""

from marketplace_mcp.core.capabilities import (
    CapabilityName,
    CapabilityState,
    capabilities_for,
)
from marketplace_mcp.core.capability_tools import marketplace_capabilities
from marketplace_mcp.core.errors import CapabilityUnavailableError, ErrorCode


def test_every_marketplace_describes_every_capability() -> None:
    manifests = capabilities_for()

    assert [manifest.marketplace for manifest in manifests] == ["ozon", "wildberries", "yandex_market"]
    assert all(
        {capability.name for capability in manifest.capabilities} == set(CapabilityName) for manifest in manifests
    )


def test_gated_and_unavailable_capabilities_explain_their_constraint() -> None:
    for manifest in capabilities_for():
        for capability in manifest.capabilities:
            if capability.state is CapabilityState.AVAILABLE:
                assert capability.tools
            else:
                assert capability.detail


def test_yandex_write_capabilities_name_their_required_setting() -> None:
    manifest = capabilities_for("yandex_market")[0]
    writes = {capability.name: capability for capability in manifest.capabilities}

    assert writes[CapabilityName.CART_WRITE].state is CapabilityState.GATED
    assert "YANDEX_MARKET_ENABLE_WRITES" in writes[CapabilityName.CART_WRITE].detail


def test_capability_tool_can_select_one_marketplace() -> None:
    result = marketplace_capabilities("wildberries")

    assert [manifest.marketplace for manifest in result] == ["wildberries"]


def test_capability_unavailable_is_a_branchable_error() -> None:
    error = CapabilityUnavailableError("wildberries", "product_search")

    assert error.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert str(error).startswith("[capability_unavailable]")
