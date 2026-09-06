"""Static structure tests for the "Línea de tiempo" tab (quick task 260906-nap).

Mirrors tests/test_timeline_fetch_all.py: source assertions only, no DB.
Guards the wiring contract between index.html and the external
linea-tiempo.js renderer, plus an untouched-view guard for the existing
Cronología timeline.
"""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "eth_pipeline" / "static" / "index.html"
LINEA_TIEMPO_JS = ROOT / "src" / "eth_pipeline" / "static" / "linea-tiempo.js"

TABLEAU20_TUPLES = [
    "[31,119,180]", "[174,199,232]", "[255,127,14]", "[255,187,120]",
    "[44,160,44]", "[152,223,138]", "[214,39,40]", "[255,152,150]",
    "[148,103,189]", "[197,176,213]", "[140,86,75]", "[196,156,148]",
    "[227,119,194]", "[247,182,210]", "[127,127,127]", "[199,199,199]",
    "[188,189,34]", "[219,219,141]", "[23,190,207]", "[158,218,229]",
]


def test_index_html_has_tab_wiring():
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'data-tab="lineatiempo"' in source, (
        "Nav button for the Línea de tiempo tab missing from index.html"
    )
    assert 'id="tab-lineatiempo"' in source, (
        "Section for the Línea de tiempo tab missing from index.html"
    )
    assert "lineatiempo: document.getElementById('tab-lineatiempo')" in source, (
        "sections map entry missing for the lineatiempo tab"
    )
    assert "window.renderLineaTiempo" in source, (
        "onTabClick does not call window.renderLineaTiempo for the new tab"
    )
    assert '<script src="linea-tiempo.js"></script>' in source, (
        "Script tag for linea-tiempo.js missing from index.html"
    )
    # The external script must load AFTER the inline app script.
    script_tag = source.index('<script src="linea-tiempo.js"></script>')
    inline_end = source.rindex("</script>", 0, script_tag)
    assert script_tag > inline_end, (
        "linea-tiempo.js must be loaded after the inline app script "
        "(globals fetchWithC/showEventDetail must be defined first)"
    )


def test_linea_tiempo_js_contents():
    assert LINEA_TIEMPO_JS.exists(), "linea-tiempo.js is missing"
    source = LINEA_TIEMPO_JS.read_text(encoding="utf-8")

    for tuple_str in TABLEAU20_TUPLES:
        assert tuple_str in source, (
            f"tableau20 tuple {tuple_str} missing from linea-tiempo.js"
        )
    assert "showEventDetail(" in source, (
        "linea-tiempo.js must open the existing detail view on click"
    )
    assert "149" in source and "92" in source, (
        "linea-tiempo.js must keep the 149x92 event rectangle dimensions"
    )
    assert "fetchWithC" in source, (
        "linea-tiempo.js must fetch through the shared passcode wrapper"
    )
    assert "renderLineaTiempo" in source, (
        "linea-tiempo.js must expose window.renderLineaTiempo"
    )


def test_linea_tiempo_js_month_labels_spanish():
    source = LINEA_TIEMPO_JS.read_text(encoding="utf-8")
    for month in ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
                  "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"):
        assert f"'{month}'" in source, (
            f"Spanish 3-letter month '{month}' missing from MONTHS3"
        )
    for en in ("'Jan'", "'Apr'", "'Aug'", "'Dec'"):
        assert en not in source, f"English month label {en} still present"


def test_linea_tiempo_js_remaining_space_layout():
    """Layout must guarantee room for all remaining items of the month."""
    source = LINEA_TIEMPO_JS.read_text(encoding="utf-8")
    assert "remaining * (EVENT_H + EVENT_GAP)" in source, (
        "layoutMonthEvents must check remaining space fits all remaining "
        "items (remaining * (EVENT_H + EVENT_GAP))"
    )
    # Backward cascade: earlier items shift up when a later item is clamped.
    assert "ys[j + 1] - (EVENT_H + EVENT_GAP)" in source, (
        "layoutMonthEvents must cascade positions backwards so an earlier "
        "item never overlaps a shifted later one"
    )


def test_linea_tiempo_js_event_when_background():
    source = LINEA_TIEMPO_JS.read_text(encoding="utf-8")
    assert "eventWhenBg" in source, (
        "linea-tiempo.js must render the background day/hour watermark"
    )
    assert ".lt2-event-when" in source, (
        "CSS for the .lt2-event-when background watermark is missing"
    )
    for day in ("'Dom'", "'Lun'", "'Mié'", "'Sáb'"):
        assert day in source, (
            f"Spanish 3-letter weekday {day} missing from DAYS3"
        )


def test_renderer_stays_out_of_inline_script():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "TABLEAU20" not in source, (
        "The renderer leaked into index.html — all new-view JS must live "
        "in static/linea-tiempo.js"
    )


def test_existing_cronologia_view_untouched():
    """Guard: the existing Cronología rendering must remain in place."""
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "function renderEventosTimeline" in source, (
        "renderEventosTimeline disappeared — the existing Cronología view "
        "must not be modified or removed"
    )
    assert ".tl-dot {" in source, (
        "tl-dot CSS missing — the existing Cronología view must stay intact"
    )
    assert "Sin fecha" in source, (
        "The existing undated list in the Cronología view must stay intact"
    )
