"""Static structure tests for hash-based navigation + tab-bar cleanup (quick task 260906-s7d).

Mirrors tests/test_linea_tiempo.py: source assertions only, no DB.
Guards the tab order, the universal refresh button, the hash navigation
state machine in index.html, and the scroll-month memory hooks in
linea-tiempo.js.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "src" / "eth_pipeline" / "static" / "index.html"
LINEA_TIEMPO_JS = ROOT / "src" / "eth_pipeline" / "static" / "linea-tiempo.js"

# Tab order fixed by the plan: Documentos, Línea de tiempo, Mapa, Eventos
# (Cargar after Eventos; Registros hidden, last).
TAB_ORDER = ["documents", "lineatiempo", "mapa", "eventos", "upload", "logs"]

# Content sections whose repeated title headers were removed.
HEADER_LESS_SECTIONS = ["tab-documents", "tab-eventos", "tab-mapa", "tab-lineatiempo"]


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_body(source: str, section_id: str) -> str:
    """Extract the <section id="...">...</section> body."""
    start = source.index(f'<section id="{section_id}"')
    end = source.index("</section>", start)
    return source[start:end]


def _inline_app_script(source: str) -> str:
    """Extract the inline app <script> body (first bare <script> tag)."""
    open_tag = "<script>"
    start = source.index(open_tag) + len(open_tag)
    end = source.index("</script>", start)
    return source[start:end]


def test_tab_button_order():
    source = _source(INDEX_HTML)
    positions = {
        tab: source.index(f'data-tab="{tab}"') for tab in TAB_ORDER
    }
    for earlier, later in zip(TAB_ORDER, TAB_ORDER[1:]):
        assert positions[earlier] < positions[later], (
            f"Tab '{earlier}' must come before '{later}' in the nav bar "
            f"(expected order: {TAB_ORDER})"
        )


def test_global_refresh_button_present_in_nav():
    source = _source(INDEX_HTML)
    nav_start = source.index("<nav")
    nav_end = source.index("</nav>", nav_start)
    nav = source[nav_start:nav_end]
    assert 'id="global-refresh-btn"' in nav, (
        "Universal refresh button missing from the nav bar"
    )
    assert 'aria-label="Actualizar"' in nav, (
        "Universal refresh button must have aria-label Actualizar"
    )
    # Pushed to the far right via margin-left:auto.
    assert "#global-refresh-btn" in source and "margin-left: auto" in source, (
        "CSS rule #global-refresh-btn { margin-left:auto } missing"
    )


def test_nav_css_is_flex_row():
    source = _source(INDEX_HTML)
    nav_css = source[source.index("    nav {"):source.index("    nav button {")]
    assert "display: flex" in nav_css and "align-items: center" in nav_css, (
        "nav must lay out buttons in a flex row with centered alignment"
    )


@pytest.mark.parametrize("removed_id", [
    "doc-refresh-btn",
    "eventos-refresh-btn",
    "lineatiempo-refresh-btn",
])
def test_per_tab_refresh_buttons_removed(removed_id: str):
    source = _source(INDEX_HTML)
    assert removed_id not in source, (
        f"Per-tab refresh button '{removed_id}' must be removed "
        "(replaced by the universal nav refresh button)"
    )


def test_no_repeated_title_headers_in_content_sections():
    source = _source(INDEX_HTML)
    for section_id in HEADER_LESS_SECTIONS:
        body = _section_body(source, section_id)
        assert 'class="documents-header"' not in body, (
            f"{section_id} still repeats its tab title as an in-content "
            "header — remove the documents-header block"
        )


def test_color_subtitle_removed():
    source = _source(INDEX_HTML)
    assert "Los colores por modelo" not in source, (
        "The Línea de tiempo color subtitle must be removed"
    )


def test_no_lt2_leakage_into_index_html():
    source = _source(INDEX_HTML)
    assert "lt2-" not in source, (
        "The linea-tiempo renderer leaked into index.html"
    )


def test_inline_app_script_syntax():
    """Syntax gate: the inline app script must be valid JavaScript."""
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    source = _source(INDEX_HTML)
    script_body = _inline_app_script(source)
    fd, tmp_path = tempfile.mkstemp(suffix=".js")
    tmp = pathlib.Path(tmp_path)
    tmp.write_text(script_body, encoding="utf-8")
    try:
        result = subprocess.run(
            ["node", "--check", str(tmp)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Inline app script has a JavaScript syntax error:\n{result.stderr}"
        )
    finally:
        tmp.unlink(missing_ok=True)


def test_refresh_hook_clears_caches():
    source = _source(LINEA_TIEMPO_JS)
    start = source.index("window.refreshLineaTiempo = function")
    body = source[start:source.index("};", start)]
    assert "lt2Events = null" in body and "lt2ColorIndex = null" in body, (
        "window.refreshLineaTiempo must clear both caches before re-rendering"
    )
    assert "renderLineaTiempo(true)" in body, (
        "window.refreshLineaTiempo must force a re-render"
    )


# ---------------------------------------------------------------------------
# Hash-based navigation
# ---------------------------------------------------------------------------

HASH_TABS = ["upload", "documents", "lineatiempo", "mapa", "eventos", "logs"]


def test_hash_state_machine_identifiers_exist():
    script = _inline_app_script(_source(INDEX_HTML))
    for identifier in ("function parseHash", "function applyHash", "function syncHash"):
        assert identifier in script, f"Missing {identifier}() in the inline app script"


def test_hash_tab_whitelist_present():
    script = _inline_app_script(_source(INDEX_HTML))
    assert "HASH_TABS" in script, (
        "Tab whitelist constant missing from the hash navigation code"
    )
    for tab in HASH_TABS:
        assert f"'{tab}'" in script, f"Tab '{tab}' missing from the whitelist"


def test_hash_option_values_never_reach_html():
    """T-S7D-01: hash values must only flow into comparisons/select.value."""
    script = _inline_app_script(_source(INDEX_HTML))
    assert "function parseHash" in script
    # No innerHTML assignment inside the hash functions.
    for fn in ("function parseHash", "function applyHash", "function syncHash"):
        start = script.index(fn)
        end = script.index("\n    }", start)
        body = script[start:end]
        assert "innerHTML" not in body, (
            f"{fn}() must never build HTML from hash values (T-S7D-01)"
        )


def test_hashchange_listener_registered():
    script = _inline_app_script(_source(INDEX_HTML))
    assert "addEventListener('hashchange'" in script, (
        "The app must react to browser back/forward via a hashchange listener"
    )
    assert "lastWrittenHash" in script, (
        "Own hash writes must be skipped by the hashchange handler (loop guard)"
    )


def test_switch_tab_syncs_hash():
    script = _inline_app_script(_source(INDEX_HTML))
    start = script.index("function switchTab")
    body = script[start:script.index("\n    }", start)]
    assert "syncHash()" in body, "switchTab must sync the URL hash"


def test_set_eventos_view_shared_by_toggle_and_apply_hash():
    script = _inline_app_script(_source(INDEX_HTML))
    assert "function setEventosView" in script, (
        "setEventosView helper must be extracted from the view-toggle handler"
    )
    # Used by both the view-toggle click handler and applyHash.
    assert re.search(r"setEventosView\([^)]*refetch", script), (
        "setEventosView must accept a refetch option (applyHash restores "
        "the view without refetching)"
    )
    start = script.index("document.getElementById('eventos-view-toggle')")
    handler = script[start:script.index("});", start)]
    assert "setEventosView(" in handler, (
        "The view-toggle click handler must route through setEventosView"
    )


def test_doc_filter_change_syncs_hash():
    script = _inline_app_script(_source(INDEX_HTML))
    start = script.index("eventosDocFilter.addEventListener('change'")
    handler = script[start:script.index("});", start)]
    assert "syncHash()" in handler, (
        "The eventos document filter change handler must sync the hash"
    )


def test_event_detail_updates_hash():
    """Hash sync lives in openEventDetail (showEventDetail routes there) and
    hideEventDetail (which routes to closeTimelineEventDetail for the
    timeline context)."""
    script = _inline_app_script(_source(INDEX_HTML))
    for fn in ("function openEventDetail", "function hideEventDetail"):
        start = script.index(fn)
        body = script[start:script.index("\n    }", start)]
        assert "syncHash()" in body, (
            f"{fn}() must update the URL hash via syncHash()"
        )
    # The eventos-context entry point must remain for existing callers.
    assert "function showEventDetail" in script
    start = script.index("function showEventDetail")
    body = script[start:script.index("\n    }", start)]
    assert "openEventDetail(eventId, 'eventos')" in body, (
        "showEventDetail() must route through openEventDetail in the "
        "eventos context"
    )


def test_hash_option_regex_guards():
    """T-S7D-01: option values are validated before use."""
    script = _inline_app_script(_source(INDEX_HTML))
    start = script.index("function applyHash")
    body = script[start:script.index("\n    function ", start) if "\n    function " in script[start:] else len(script)]
    assert "/^[A-Za-z0-9_-]+$/.test(opts.doc)" in body, (
        "applyHash must validate the doc option against ^[A-Za-z0-9_-]+$"
    )
    assert "/^[A-Za-z0-9-]+$/.test(state.options.event)" in body, (
        "applyHash must validate the event option against ^[A-Za-z0-9-]+$"
    )


def test_apply_hash_guards_logs_tab():
    script = _inline_app_script(_source(INDEX_HTML))
    start = script.index("function applyHash")
    body = script[start:script.index("\n    }", start)]
    assert "logsDocumentId" in body, (
        "applyHash must not switch to the logs tab without an open document"
    )


# ---------------------------------------------------------------------------
# Línea de tiempo scroll-month memory
# ---------------------------------------------------------------------------

def test_linea_tiempo_scroll_memory_hooks():
    source = _source(LINEA_TIEMPO_JS)
    for identifier in (
        "function getMonthAnchors",
        "lt2SavedMonth",
        "window.restoreLineaTiempoScroll",
        "window.refreshLineaTiempo",
    ):
        assert identifier in source, (
            f"Missing {identifier} in linea-tiempo.js"
        )
    assert "addEventListener('scroll'" in source, (
        "linea-tiempo.js must track the scroll position with a window "
        "scroll listener"
    )


def test_scroll_listener_only_tracks_active_tab():
    source = _source(LINEA_TIEMPO_JS)
    start = source.index("window.addEventListener('scroll'")
    body = source[start:source.index("}, { passive: true })", start)]
    assert "tab-lineatiempo" in body or "lineatiempoActive()" in body, (
        "The scroll listener must no-op unless the Línea de tiempo tab is active"
    )


def test_restore_uses_month_label_match():
    source = _source(LINEA_TIEMPO_JS)
    start = source.index("window.restoreLineaTiempoScroll = function")
    body = source[start:source.index("};", start)]
    assert "lt2SavedMonth" in body, (
        "Restore must target the saved month label"
    )
    assert "window.scrollTo" in body, (
        "Restore must scroll the window back to the anchor position"
    )


def test_month_anchors_use_label_text_and_doc_top():
    source = _source(LINEA_TIEMPO_JS)
    start = source.index("function getMonthAnchors")
    body = source[start:source.index("\n  }", start)]
    assert ".lt2-month-label" in body, (
        "Anchors must come from the rendered month labels"
    )
    assert "getBoundingClientRect" in body and "window.scrollY" in body, (
        "Anchor tops must be document-space (rect.top + window.scrollY)"
    )
    assert "textContent" in body, (
        "Anchors must carry the label text (e.g. 'Ene 2026')"
    )
