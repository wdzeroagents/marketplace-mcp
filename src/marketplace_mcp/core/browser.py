"""One Playwright driver shared by browser-backed adapters."""

import atexit
from functools import cache

from playwright.sync_api import Playwright, sync_playwright


@cache
def get_playwright() -> Playwright:
    """Return the shared Playwright driver for the session worker thread.

    Browser operations run on the dedicated single-thread executor in
    ``core.dependencies``. Playwright's sync driver must be created and used
    on that same thread.
    """
    return sync_playwright().start()


def _stop_playwright() -> None:
    """Stop the shared driver after adapter shutdown handlers have run."""
    if get_playwright.cache_info().currsize:
        get_playwright().stop()


# Register during import, before adapters register their context cleanup.
# Atexit runs later registrations first, so adapter contexts close before the
# shared driver stops.
atexit.register(_stop_playwright)
