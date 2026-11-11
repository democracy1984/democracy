def test_main_imports_and_registers_handlers():
    import main

    handlers = main.client.list_event_handlers()
    assert len(handlers) >= 7


def test_tools_import():
    import tools.backfill_names  # noqa: F401
    import tools.getchatid  # noqa: F401
