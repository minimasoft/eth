"""Regression test guarding the Cronología (timeline) fetch-all fix (quick task 260905-to0).

The timeline view must render ALL events matching the current filters/search,
not just the first 100. These assertions verify:
  1. A fetchAllEventos() helper exists in the Eventos UI script.
  2. The helper loops over /events pages (data.pages) accumulating items.
  3. fetchEventos() delegates to the helper when the view mode is timeline.
  4. The old current-page qualifier note ("página actual") is gone.
  5. The table render path (renderEventos) still exists in fetchEventos.
  6. The API's server-side per_page cap (le=100) is still in place.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "eth_pipeline" / "static" / "index.html"
EVENTS_V2 = ROOT / "src" / "eth_pipeline" / "api" / "routes" / "events_v2.py"


def _extract_function(source: str, signature: str, end_marker: str) -> str:
    """Return the source slice from `signature` up to (excluding) `end_marker`."""
    start = source.index(signature)
    end = source.index(end_marker, start)
    return source[start:end]


def test_timeline_fetch_all_wiring():
    source = INDEX_HTML.read_text(encoding="utf-8")

    # 1. fetchAllEventos helper is defined.
    assert "async function fetchAllEventos()" in source, (
        "fetchAllEventos() helper missing from index.html — timeline would "
        "render only the first page of events"
    )

    # 2. The helper loops over pages and accumulates items.
    helper_body = _extract_function(
        source,
        "async function fetchAllEventos()",
        "function renderEventos(",
    )
    assert "data.pages" in helper_body, (
        "fetchAllEventos() does not read data.pages — it would stop after page 1"
    )
    assert "allItems.push(" in helper_body or "allItems.concat(" in helper_body, (
        "fetchAllEventos() does not accumulate items across pages"
    )

    # 3. fetchEventos delegates to the helper in timeline mode.
    fetch_body = _extract_function(
        source,
        "async function fetchEventos()",
        "async function fetchAllEventos()",
    )
    assert "eventosViewMode === 'timeline'" in fetch_body, (
        "fetchEventos() no longer branches on the timeline view mode"
    )
    assert "fetchAllEventos()" in fetch_body, (
        "fetchEventos() does not delegate to fetchAllEventos() in timeline mode"
    )

    # 4. The old current-page qualifier note is gone from the whole file.
    assert "página actual" not in source, (
        "timeline note still shows the 'página actual' page qualifier — "
        "should report the total event count plainly"
    )

    # 5. The table render path still exists in fetchEventos' non-timeline branch.
    assert "renderEventos(data)" in fetch_body, (
        "fetchEventos() no longer calls renderEventos() — table view broken"
    )

    # 6. The API's server-side per_page cap is still in place.
    api_source = EVENTS_V2.read_text(encoding="utf-8")
    assert "le=100" in api_source, (
        "events_v2.py per_page cap (le=100) was removed — unbounded per_page "
        "is a DoS vector and must not be raised"
    )
