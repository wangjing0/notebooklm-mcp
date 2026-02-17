import asyncio
from typing import Optional

from playwright.async_api import Page

from .logger import log

RESPONSE_SELECTORS = [
    ".to-user-container .message-text-content",
    "[data-message-author='bot']",
    "[data-message-author='assistant']",
    "[data-message-role='assistant']",
    "[data-author='assistant']",
    "[data-renderer*='assistant']",
    "[data-automation-id='response-text']",
    "[data-automation-id='assistant-response']",
    "[data-automation-id='chat-response']",
    "[data-testid*='assistant']",
    "[data-testid*='response']",
    "[aria-live='polite']",
    "[role='listitem'][data-message-author]",
]


def _hash_string(s: str) -> int:
    h = 0
    for ch in s:
        h = (((h << 5) - h) + ord(ch)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return h


async def snapshot_all_responses(page: Page) -> list[str]:
    all_texts: list[str] = []
    try:
        containers = await page.query_selector_all(".to-user-container")
        for container in containers:
            try:
                text_el = await container.query_selector(".message-text-content")
                if text_el:
                    text = await text_el.inner_text()
                    if text and text.strip():
                        all_texts.append(text.strip())
            except Exception:
                continue
        log.info(f"  Captured {len(all_texts)} existing responses")
    except Exception as e:
        log.warning(f"  Failed to snapshot responses: {e}")
    return all_texts


async def _extract_latest_text(
    page: Page,
    known_hashes: set,
    debug: bool,
    poll_count: int,
) -> Optional[str]:
    try:
        containers = await page.query_selector_all(".to-user-container")
        total = len(containers)

        if total <= len(known_hashes):
            return None

        for idx, container in enumerate(containers):
            try:
                text_el = await container.query_selector(".message-text-content")
                if text_el:
                    text = await text_el.inner_text()
                    if text and text.strip():
                        text_hash = _hash_string(text.strip())
                        if text_hash not in known_hashes:
                            log.success(f"  Found NEW text in container[{idx}]: {len(text.strip())} chars")
                            return text.strip()
            except Exception:
                continue
        return None
    except Exception as e:
        log.error(f"  Primary selector failed: {e}")

    for selector in RESPONSE_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for element in elements:
                try:
                    text = await element.inner_text()
                    if text and text.strip() and _hash_string(text.strip()) not in known_hashes:
                        return text.strip()
                except Exception:
                    continue
        except Exception:
            continue

    return None


async def wait_for_latest_answer(
    page: Page,
    question: str = "",
    timeout_ms: int = 120000,
    poll_interval_ms: int = 1000,
    ignore_texts: Optional[list[str]] = None,
    debug: bool = False,
) -> Optional[str]:
    import time

    deadline = time.time() + timeout_ms / 1000
    sanitized_question = question.strip().lower()
    known_hashes: set = set()
    for text in (ignore_texts or []):
        if isinstance(text, str) and text.strip():
            known_hashes.add(_hash_string(text.strip()))

    poll_count = 0
    last_candidate: Optional[str] = None
    stable_count = 0
    required_stable = 3

    while time.time() < deadline:
        poll_count += 1

        try:
            thinking = await page.query_selector("div.thinking-message")
            if thinking and await thinking.is_visible():
                await asyncio.sleep(poll_interval_ms / 1000)
                continue
        except Exception:
            pass

        candidate = await _extract_latest_text(page, known_hashes, debug, poll_count)

        if candidate:
            normalized = candidate.strip()
            if normalized:
                if normalized.lower() == sanitized_question:
                    known_hashes.add(_hash_string(normalized))
                    await asyncio.sleep(poll_interval_ms / 1000)
                    continue

                if normalized == last_candidate:
                    stable_count += 1
                else:
                    stable_count = 1
                    last_candidate = normalized

                if stable_count >= required_stable:
                    return normalized

        await asyncio.sleep(poll_interval_ms / 1000)

    return None
