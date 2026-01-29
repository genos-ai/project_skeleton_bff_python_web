"""
End-to-End Test Fixtures.

Fixtures for E2E tests - full stack including frontend interactions.
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def e2e_client() -> AsyncGenerator[AsyncClient, None]:
    """Create a client for E2E testing."""
    from modules.backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# Add Playwright fixtures here when E2E browser testing is needed:
#
# @pytest.fixture
# async def browser():
#     """Create a browser instance for E2E testing."""
#     from playwright.async_api import async_playwright
#
#     async with async_playwright() as p:
#         browser = await p.chromium.launch()
#         yield browser
#         await browser.close()
#
#
# @pytest.fixture
# async def page(browser):
#     """Create a new page for E2E testing."""
#     page = await browser.new_page()
#     yield page
#     await page.close()
