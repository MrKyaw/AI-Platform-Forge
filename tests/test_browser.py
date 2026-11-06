"""Browser acceptance with a deterministic model boundary, not model-quality evaluation."""

import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from forge.app import create_app
from forge.config import Settings
from tests.conftest import FakeOllama


@contextmanager
def running_server(data_dir: Path, provider: FakeOllama):
    app = create_app(Settings(data_dir), provider)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "test server did not stop"


@pytest.mark.browser
def test_complete_browser_journey_and_restart(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        provider = FakeOllama()
        with running_server(data, provider) as url:
            page.goto(url)
            expect(page.get_by_text("Your library is empty.", exact=False)).to_be_visible()
            expect(page.locator("#model-status")).to_contain_text("Local models ready")
            page.get_by_label("Add a document", exact=True).set_input_files(
                {
                    "name": "launch.md",
                    "mimeType": "text/markdown",
                    "buffer": b"# Launch\nThe launch code is cedar.",
                }
            )
            page.get_by_role("button", name="Upload document").click()
            expect(page.locator("#documents")).to_contain_text("ready", timeout=15000)
            page.get_by_label("What would you like to know?").fill("What is the launch code?")
            page.get_by_role("button", name="Ask a question").click()
            expect(page.locator("#run-status")).to_have_text("COMPLETED", timeout=15000)
            expect(page.locator("#answer")).to_have_text("The launch code is cedar.")
            page.get_by_role("button", name="1. launch.md · p. 1").click()
            expect(page.locator("#source-dialog")).to_be_visible()
            expect(page.locator("#source-text")).to_contain_text("cedar")
            page.keyboard.press("Escape")
            expect(page.locator("#source-dialog")).not_to_be_visible()
            provider.delay = 5
            page.get_by_label("What would you like to know?").fill("Tell me the launch code again.")
            page.get_by_role("button", name="Ask a question").click()
            page.get_by_role("button", name="Stop", exact=True).click()
            expect(page.locator("#run-status")).to_have_text("CANCELLED", timeout=10000)
            expect(page.locator("#answer")).to_contain_text("cancelled")
            page.reload()
            expect(page.locator("#history")).to_contain_text("What is the launch code?")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.keyboard.press("Tab")
            expect(page.get_by_role("link", name="Skip to question")).to_be_focused()
            page.keyboard.press("Enter")
            expect(page.locator("#question")).to_be_focused()
            page.set_viewport_size({"width": 1440, "height": 1100})
            Path(".cache").mkdir(exist_ok=True)
            page.screenshot(path=".cache/browser-desktop.png", full_page=True)
        with running_server(data, FakeOllama()) as url:
            page.goto(url)
            expect(page.locator("#history")).to_contain_text("What is the launch code?")
            page.get_by_role("button", name="What is the launch code?", exact=True).click()
            expect(page.locator("#answer")).to_have_text("The launch code is cedar.")
            page.once("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Delete launch.md", exact=True).click()
            expect(page.locator("#documents")).to_contain_text("Your library is empty.")
            expect(page.locator("#answer")).to_contain_text("removed with its source")
            expect(page.locator("#history")).not_to_contain_text("What is the launch code?")
        assert not errors
        browser.close()


@pytest.mark.browser
def test_unavailable_models_and_safe_rendering(tmp_path: Path) -> None:
    provider = FakeOllama()
    provider.failure = "models"
    with running_server(tmp_path, provider) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(url)
        expect(page.locator("#model-status")).to_contain_text("ollama pull")
        expect(page.get_by_role("button", name="Ask a question")).to_be_disabled()
        expect(page.get_by_label("What would you like to know?")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()
