import asyncio
from io import BytesIO
import threading

import pytest

from akinator_core_test.game import GameState, Guess
from akinator_core_test import raster, render

Image = pytest.importorskip("PIL.Image")
ImageFont = pytest.importorskip("PIL.ImageFont")


@pytest.fixture(autouse=True)
def portable_font(monkeypatch):
    # Layout tests do not depend on a runner having installed Chinese fonts.
    # The production preview separately verifies real CJK glyphs.
    fonts = {size: ImageFont.load_default(size=size) for size in (17, 18, 19, 21, 22, 32)}
    monkeypatch.setattr(raster, "font_path", lambda: "unused")
    monkeypatch.setattr(ImageFont, "truetype", lambda path, size: fonts[size])


@pytest.mark.parametrize("mode", ["day", "night"])
@pytest.mark.parametrize("kind", ["question", "guess"])
def test_local_cards_are_complete_pngs_in_both_themes(mode, kind):
    state = GameState(question="A long question " * 12, answer_depth=2)
    photo = None
    if kind == "guess":
        state.guess = Guess("1", "A person " * 12, "A description " * 25, pseudo="Photographer")
        picture = BytesIO()
        Image.new("RGB", (200, 150), "red").save(picture, format="PNG")
        photo = ("image/png", picture.getvalue())
    result = raster.render_png(state, theme={"palette_mode": mode}, photo=photo)
    with Image.open(BytesIO(result)) as image:
        image.load()
        assert image.format == "PNG" and image.width == 1230
        assert 500 < image.height < 2500
        assert image.getpixel((0, 0)) == ((18, 24, 39) if mode == "night" else (241, 237, 249))
        if photo:
            assert any(color == (255, 0, 0) for count, color in image.getcolors(image.width * image.height))
    assert state.question_number == 3 and state.answer_depth == 2


async def test_stalled_browser_is_cancelled_and_same_question_still_returns_image(monkeypatch):
    cancelled = asyncio.Event()
    async def stalled_capture(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    original_wait = asyncio.wait_for
    async def short_wait(coro, timeout):
        assert timeout == 13
        return await original_wait(coro, .01)
    monkeypatch.setattr(render, "HTML_RENDER_AVAILABLE", True)
    monkeypatch.setattr(render, "capture_html", stalled_capture)
    monkeypatch.setattr(render.asyncio, "wait_for", short_wait)
    monkeypatch.setattr(render, "theme_context", lambda host: {"palette_mode": "night"})
    original_render = raster.render_png
    loop_thread = threading.get_ident()
    def off_loop(*args, **kwargs):
        assert threading.get_ident() != loop_thread
        return original_render(*args, **kwargs)
    monkeypatch.setattr(raster, "render_png", off_loop)
    state = GameState(question="The same question")
    result = await render.render_card(state)
    assert cancelled.is_set()
    with Image.open(BytesIO(result)) as image:
        image.verify()
    assert state.question == "The same question" and state.question_number == 1


async def test_cancellation_does_not_start_another_renderer(monkeypatch):
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError()
    monkeypatch.setattr(render, "HTML_RENDER_AVAILABLE", True)
    monkeypatch.setattr(render, "capture_html", cancelled)
    monkeypatch.setattr(raster, "render_png", lambda *args, **kwargs: pytest.fail("cancelled game rendered again"))
    with pytest.raises(asyncio.CancelledError):
        await render.render_card(GameState(question="Cancelled"))


async def test_pillow_alone_can_render_without_htmlrender_or_private_utils(monkeypatch):
    monkeypatch.setattr(render, "HTML_RENDER_AVAILABLE", False)
    result = await render.render_card(GameState(question="Portable"), host=False)
    with Image.open(BytesIO(result)) as image:
        image.verify()


def test_invalid_optional_portrait_does_not_suppress_card():
    state = GameState(guess=Guess("1", "Person", "Description"))
    result = raster.render_png(state, photo=("image/png", b"broken"))
    with Image.open(BytesIO(result)) as image:
        image.verify()
