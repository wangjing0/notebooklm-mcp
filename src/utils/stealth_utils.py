import asyncio
import math
import random
from typing import Optional

from playwright.async_api import Page

from ..config import CONFIG


async def _sleep(ms: float) -> None:
    await asyncio.sleep(ms / 1000)


def _random_float(min_val: float, max_val: float) -> float:
    return random.uniform(min_val, max_val)


def _random_int(min_val: int, max_val: int) -> int:
    return random.randint(min_val, max_val)


def _random_char() -> str:
    chars = "qwertyuiopasdfghjklzxcvbnm"
    return random.choice(chars)


async def random_delay(min_ms: Optional[float] = None, max_ms: Optional[float] = None) -> None:
    min_ms = min_ms if min_ms is not None else CONFIG.minDelayMs
    max_ms = max_ms if max_ms is not None else CONFIG.maxDelayMs

    if not CONFIG.stealthEnabled or not CONFIG.stealthRandomDelays:
        target = min_ms if min_ms == max_ms else (min_ms + max_ms) / 2
        if target > 0:
            await _sleep(target)
        return

    mean = min_ms + (max_ms - min_ms) * 0.6
    std_dev = (max_ms - min_ms) * 0.2
    delay = random.gauss(mean, std_dev)
    delay = max(min_ms, min(max_ms, delay))
    await _sleep(delay)


async def human_type(
    page: Page,
    selector: str,
    text: str,
    wpm: Optional[int] = None,
    with_typos: bool = True,
) -> None:
    if not CONFIG.stealthEnabled or not CONFIG.stealthHumanTyping:
        await page.fill(selector, text)
        return

    effective_wpm = wpm if wpm is not None else _random_int(CONFIG.typingWpmMin, CONFIG.typingWpmMax)
    chars_per_minute = effective_wpm * 5
    avg_delay_ms = (60 * 1000) / chars_per_minute

    await page.fill(selector, "")
    await random_delay(30, 80)
    await page.click(selector)
    await random_delay(20, 60)

    current_text = ""
    i = 0
    while i < len(text):
        char = text[i]

        if with_typos and random.random() < 0.003 and i > 0:
            wrong_char = _random_char()
            current_text += wrong_char
            await page.fill(selector, current_text)
            notice_delay = _random_float(avg_delay_ms * 0.6, avg_delay_ms * 1.1)
            await _sleep(notice_delay)
            current_text = current_text[:-1]
            await page.fill(selector, current_text)
            await random_delay(20, 60)

        current_text += char
        await page.fill(selector, current_text)

        if char in ".!?":
            delay = _random_float(avg_delay_ms * 1.05, avg_delay_ms * 1.4)
        elif char == " ":
            delay = _random_float(avg_delay_ms * 0.5, avg_delay_ms * 0.9)
        elif char == ",":
            delay = _random_float(avg_delay_ms * 0.9, avg_delay_ms * 1.2)
        else:
            variation = _random_float(0.5, 0.9)
            delay = avg_delay_ms * variation

        await _sleep(delay)
        i += 1

    await random_delay(50, 120)


async def random_mouse_movement(
    page: Page,
    target_x: Optional[float] = None,
    target_y: Optional[float] = None,
    steps: Optional[int] = None,
) -> None:
    if not CONFIG.stealthEnabled or not CONFIG.stealthMouseMovements:
        return

    viewport = page.viewport_size or {"width": CONFIG.viewport.width, "height": CONFIG.viewport.height}
    vw = viewport["width"]
    vh = viewport["height"]

    tx = target_x if target_x is not None else _random_int(100, vw - 100)
    ty = target_y if target_y is not None else _random_int(100, vh - 100)
    n_steps = steps if steps is not None else _random_int(10, 25)

    start_x = _random_int(0, vw)
    start_y = _random_int(0, vh)

    for step in range(n_steps):
        progress = step / n_steps
        curve_x = math.sin(progress * math.pi) * _random_int(-50, 50)
        curve_y = math.cos(progress * math.pi) * _random_int(-30, 30)

        cx = start_x + (tx - start_x) * progress + curve_x + _random_float(-3, 3)
        cy = start_y + (ty - start_y) * progress + curve_y + _random_float(-3, 3)
        cx = max(0, min(vw, cx))
        cy = max(0, min(vh, cy))

        await page.mouse.move(cx, cy)
        delay = 10 + 20 * abs(0.5 - progress)
        await _sleep(delay)


async def realistic_click(
    page: Page,
    selector: str,
    with_mouse_movement: bool = True,
) -> None:
    if not CONFIG.stealthEnabled or not CONFIG.stealthMouseMovements:
        await page.click(selector)
        return

    if with_mouse_movement:
        element = await page.query_selector(selector)
        if element:
            box = await element.bounding_box()
            if box:
                ox = _random_float(-box["width"] * 0.2, box["width"] * 0.2)
                oy = _random_float(-box["height"] * 0.2, box["height"] * 0.2)
                await random_mouse_movement(
                    page,
                    box["x"] + box["width"] / 2 + ox,
                    box["y"] + box["height"] / 2 + oy,
                )

    await random_delay(100, 300)
    await page.click(selector)
    await random_delay(150, 400)
