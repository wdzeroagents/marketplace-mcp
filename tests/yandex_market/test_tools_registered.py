from marketplace_mcp.main import mcp


def test_catalog_and_write_tools_are_registered_and_described() -> None:
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    expected = {
        "yandex_market_search",
        "yandex_market_product_details",
        "yandex_market_add_to_cart",
        "yandex_market_set_favorite",
    }
    assert expected <= tools.keys()
    for name in expected:
        assert tools[name].description
        assert all(
            isinstance(parameter.get("description"), str)
            for parameter in tools[name].parameters.get("properties", {}).values()
        )
    assert "GATED" in (tools["yandex_market_add_to_cart"].description or "")
    assert "GATED" in (tools["yandex_market_set_favorite"].description or "")
