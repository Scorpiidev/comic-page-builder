"""Balloons: shapes, text fitting, and the Letters layer in page.svg."""

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import replace

import pytest

from cpb_core.balloons import KINDS, Balloon, BalloonFont, Tail, approx_measure, fit_balloon, outline_path, wrap
from cpb_core.balloons.text import layout_lines
from cpb_core.build import page_from_bsp
from cpb_core.geometry import PageSize
from cpb_core.svg import page_to_svg, parse_page
from cpb_core.svg.ns import SVG, q

measure = approx_measure(8.0)


def speech(**kw):
    base = dict(number=1, kind="speech", cx=60, cy=50, rx=20, ry=12, text="Where did you put the map?",
                tail=Tail(tip_x=75, tip_y=85))
    base.update(kw)
    return Balloon(**base)


def subpaths(d):
    return d.count("M")


# ---------- shapes ----------
@pytest.mark.parametrize("kind", KINDS)
def test_outlines_use_only_commands_the_importers_can_map(kind):
    d = outline_path(speech(kind=kind))
    assert set(re.findall(r"[A-Za-z]", d)) <= set("MLCZ")


@pytest.mark.parametrize("kind", ["speech", "whisper", "shout"])
def test_body_and_tail_are_one_closed_path_through_the_tip(kind):
    d = outline_path(speech(kind=kind))
    assert subpaths(d) == 1 and d.endswith("Z")
    assert "75 85" in d  # the tip itself is a point on the outline


def test_thought_tail_is_a_trail_of_bubbles_ending_at_the_tip():
    d = outline_path(speech(kind="thought", tail=Tail(tip_x=66, tip_y=72)))
    assert subpaths(d) >= 3  # the cloud plus at least two bubbles (more for longer tails)


def test_longer_thought_tails_get_more_bubbles_not_wider_gaps():
    counts = [subpaths(outline_path(speech(kind="thought", tail=Tail(tip_x=60, tip_y=y)))) - 1 for y in (70, 90, 130, 400)]
    assert counts == sorted(counts) and counts[0] >= 2 and counts[-1] == 8
    assert counts[1] < counts[2]


def test_a_hand_placed_base_swings_round_when_the_body_moves_past_the_tip():
    from cpb_core.balloons import tail_base_point
    # Base dragged to the bottom of the body, tip below: fine as it is.
    b = speech(tail=Tail(tip_x=60, tip_y=85, base_angle=100))
    x, y = tail_base_point(b)
    assert y > 50 + 11  # on the bottom of the rim, where it was put
    # Move the body below the tip (tip left behind): the tail would cross the
    # body and the text, so the base comes round to the top.
    moved = b.moved(0, 60)
    x, y = tail_base_point(moved)
    assert y < moved.cy  # now on the top half, facing the tip
    assert moved.tail.base_angle == 100  # your setting is kept for when the body comes back


def test_a_tip_inside_the_body_draws_no_tail():
    b = speech(tail=Tail(tip_x=62, tip_y=52))
    assert outline_path(b) == outline_path(replace(b, tail=None))


def test_captions_never_get_a_tail():
    b = speech(kind="caption")
    assert not b.has_tail
    assert outline_path(b) == outline_path(replace(b, tail=None))


def test_shout_burst_is_the_same_every_save():
    assert outline_path(speech(kind="shout")) == outline_path(speech(kind="shout"))
    assert outline_path(speech(kind="shout", number=2)) != outline_path(speech(kind="shout"))


def test_base_angle_moves_where_the_tail_leaves_the_body():
    aimed = outline_path(speech())
    left = outline_path(speech(tail=Tail(tip_x=75, tip_y=85, base_angle=180)))
    assert aimed != left and "75 85" in left


def test_moving_the_body_leaves_the_tip_unless_it_follows():
    b = speech()
    assert b.moved(10, 0).tail.tip_x == 75
    follows = speech(tail=Tail(tip_x=75, tip_y=85, tip_follows_body=True))
    assert follows.moved(10, -5).tail.tip_x == 85 and follows.moved(10, -5).tail.tip_y == 80


def test_bad_values_are_refused():
    with pytest.raises(ValueError):
        speech(kind="scream")
    with pytest.raises(ValueError):
        Tail(tip_x=0, tip_y=0, bend=2)
    with pytest.raises(ValueError):
        speech(rx=0)


# ---------- text ----------
def test_wrap_is_greedy_and_keeps_typed_breaks():
    m = lambda s: len(s)  # one mm per character
    assert wrap("one two three four", m, 9) == ["one two", "three", "four"]
    assert wrap("HEY!\nyou there", m, 20) == ["HEY!", "you there"]
    assert wrap("supercalifragilistic is long", m, 8) == ["supercalifragilistic", "is long"]


def _corners_inside(b, block):
    hw, hh = block.width / 2, block.height / 2
    return (hw / b.rx) ** 2 + (hh / b.ry) ** 2 <= 1.0


def test_auto_size_fits_an_ellipse_around_the_text():
    b = fit_balloon(speech(text="I told you we should have turned left at the lighthouse!"), measure)
    block = layout_lines(b.lines, b, measure)
    assert len(b.lines) >= 2
    assert _corners_inside(b, block)
    assert 1.0 <= b.rx / b.ry <= 2.4  # a balloon, not a sausage


def test_turning_auto_size_off_keeps_the_size_and_rewraps():
    b = fit_balloon(speech(auto_size=False, rx=14, ry=14, text="a b c d e f g h i j k l m n o p"), measure)
    assert (b.rx, b.ry) == (14, 14)
    assert all(measure(line) <= math.sqrt(2) * (14 - 2.0) + 1e-9 for line in b.lines)


def test_empty_text_has_no_lines():
    assert fit_balloon(speech(text="   "), measure).lines == ()


# ---------- page.svg ----------
def page_with(*balloons):
    size = PageSize(trim_w=170, trim_h=260, bleed=3, safe=5, margin=8, dpi=600)
    page = page_from_bsp(7, size, 4, seed=3)
    return replace(page, balloons=balloons)


def test_balloons_round_trip_through_page_svg():
    page = page_with(speech(), speech(number=2, kind="thought", cx=100, text="Hmm."),
                     speech(number=3, kind="caption", cx=40, cy=20, text="Meanwhile...", tail=None),
                     speech(number=4, kind="whisper", text="psst\nover here", font=BalloonFont(color="#333333")))
    svg = page_to_svg(page)
    doc = parse_page(svg)
    assert [b.number for b in doc.page.balloons] == [1, 2, 3, 4]
    assert doc.page.balloons[3].text == "psst\nover here"
    assert doc.page.balloons[3].font.color == "#333333"
    assert doc.page.balloons[0].tail == Tail(tip_x=75, tip_y=85)
    assert doc.to_svg() == svg  # write, read, write: identical
    assert not doc.edited_balloons


def test_each_line_is_a_positioned_tspan():
    svg = page_to_svg(page_with(fit_balloon(speech(text="ONE TWO THREE FOUR FIVE SIX SEVEN"), measure)))
    root = ET.fromstring(svg)
    spans = [el for el in root.iter(q(SVG, "tspan"))]
    assert len(spans) >= 2
    assert all(s.get("x") and s.get("y") for s in spans)
    ys = [float(s.get("y")) for s in spans]
    assert ys == sorted(ys)


def test_whisper_is_dashed():
    svg = page_to_svg(page_with(speech(kind="whisper")))
    assert 'stroke-dasharray="1.2 0.9"' in svg


def test_saving_from_the_page_builder_keeps_the_balloons():
    svg = page_to_svg(page_with(speech()))
    doc = parse_page(svg)
    relaid = replace(doc.page, gutter=5.0, balloons=None)  # what the builder saves
    assert parse_page(doc.to_svg(relaid)).page.balloons == doc.page.balloons


def test_your_own_things_in_the_letters_layer_survive():
    svg = page_to_svg(page_with(speech()))
    svg = svg.replace('<g id="cpb-balloon-1"', '<path id="my-sfx" d="M0 0L1 1"/><g id="cpb-balloon-1"', 1)
    doc = parse_page(svg)
    out = doc.to_svg(replace(doc.page, balloons=()))
    assert 'id="my-sfx"' in out and "cpb-balloon-1" not in out


def test_words_changed_in_another_app_win():
    svg = page_to_svg(page_with(fit_balloon(speech(text="HELLO"), measure)))
    assert svg.count(">HELLO<") == 1
    doc = parse_page(svg.replace(">HELLO<", ">GOODBYE<"))
    assert doc.edited_balloons == [1]
    assert doc.page.balloons[0].text == "GOODBYE"


def test_saving_letters_leaves_panels_edited_elsewhere_alone():
    svg = page_to_svg(page_with())
    # Reshape panel 1 the way Illustrator would.
    svg = re.sub(r'(id="cpb-panel-1"[^>]*? d=")[^"]+"', r'\1M10 10L90 10L50 90Z"', svg, count=1)
    doc = parse_page(svg)
    assert doc.modified_panels == [1]
    out = doc.letters_svg([speech()])
    again = parse_page(out)
    assert again.modified_panels == [1] and [b.number for b in again.page.balloons] == [1]


def test_project_saves_balloons_and_picks_fonts_from_presets(tmp_path):
    from cpb_core.lettering import LetteringPreset
    from cpb_core.project import create_project
    p = create_project(str(tmp_path / "C"), "C", blank_pages=1, seed=1)
    assert p.balloon_font("dialogue") is None
    p.lettering["dialogue"] = LetteringPreset("Comic Neue", "Bold", 8.5, 0.71, "ComicNeue-Bold")
    f = p.balloon_font("whisper")  # no whisper preset: falls back to dialogue
    assert (f.family, f.style, f.size_pt, f.ps_name) == ("Comic Neue", "Bold", 8.5, "ComicNeue-Bold")
    p.save_balloons(1, [speech(font=f)])
    assert p.load_page(1).balloons[0].font == f


def test_two_balloons_cant_share_a_number():
    with pytest.raises(ValueError):
        page_with(speech(), speech())
