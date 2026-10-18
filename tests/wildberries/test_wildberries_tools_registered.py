from marketplace_mcp.main import mcp


def test_wildberries_and_shared_store_tools_are_registered() -> None:
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    expected = {
        "wildberries_open_login",
        "wildberries_session_status",
        "wildberries_sync_orders",
        "wildberries_sync_prices",
        "marketplace_orders",
        "marketplace_order_details",
    }
    assert expected <= tools.keys()
    for name in expected:
        assert tools[name].description
        assert all(
            isinstance(parameter.get("description"), str)
            for parameter in tools[name].parameters.get("properties", {}).values()
        )
