/* Línea de tiempo — vertical timeline view (quick task 260906-nap).
 *
 * Self-contained renderer for the "Línea de tiempo" tab. All view JS lives
 * here (index.html only wires the nav button/section/script tag). Relies on
 * the globals defined by the inline script in index.html, which is loaded
 * BEFORE this file: fetchWithC, showEventDetail, escapeHtml, showBanner,
 * truncateText.
 *
 * Exposed hooks (called from index.html):
 * - window.renderLineaTiempo()      — render (cached; force=true refetches)
 * - window.refreshLineaTiempo()     — universal nav refresh button: clears
 *                                     caches and re-renders
 * - window.restoreLineaTiempoScroll() — onTabClick calls this after render;
 *                                     scrolls back to the month the user
 *                                     had scrolled to (lt2SavedMonth)
 *
 * Layout: vertical months (old→new, top→bottom), one column per model
 * (149px + 16px gap), 149×92 event rectangles colored from the tableau20
 * palette (DB-stored color_index where available, string-hash fallback),
 * month divider lines with left "Ene 2026" labels, horizontally centered
 * with a right-side compensation element matching the left gutter width.
 */
(function () {
  'use strict';

  var TABLEAU20 = [[31,119,180],[174,199,232],[255,127,14],[255,187,120],[44,160,44],[152,223,138],[214,39,40],[255,152,150],[148,103,189],[197,176,213],[140,86,75],[196,156,148],[227,119,194],[247,182,210],[127,127,127],[199,199,199],[188,189,34],[219,219,141],[23,190,207],[158,218,229]];

  /* Layout constants (px). */
  var EVENT_W = 149;
  var EVENT_H = 92;
  var EVENT_GAP = 4;
  var COL_GAP = 16;
  var COL_STEP = EVENT_W + COL_GAP;          /* 165px per model column */
  var GUTTER_W = 90;                          /* left month-label gutter */
  var MONTH_PAD = 4;                          /* inset above/below month content */

  var MONTHS3 = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  var DAYS3 = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

  /* Caches — refetched only via the refresh button. */
  var lt2Events = null;       /* all events (array) */
  var lt2ColorIndex = null;   /* model string -> DB color_index | null */

  var lt2Loading = false;

  /* Scroll-month memory: the label of the top-most month visible when the
   * user leaves the tab, restored on re-entry. */
  var lt2SavedMonth = null;
  var SCROLL_TRACK_OFFSET = 80;   /* px below the viewport top for tracking */
  var SCROLL_RESTORE_OFFSET = 8;  /* px above the anchor when restoring */

  /* Map each rendered .lt2-month-label to its document-space top and text. */
  function getMonthAnchors() {
    var container = document.getElementById('lineatiempo-container');
    if (!container) return [];
    var anchors = [];
    var labels = container.querySelectorAll('.lt2-month-label');
    for (var i = 0; i < labels.length; i++) {
      var top = labels[i].getBoundingClientRect().top + window.scrollY;
      anchors.push({ label: labels[i].textContent, docTop: top });
    }
    return anchors;
  }

  function lineatiempoActive() {
    var section = document.getElementById('tab-lineatiempo');
    return !!(section && section.classList.contains('active'));
  }

  /* Track the top-most visible month while the tab is active. Added once —
   * a no-op whenever the Línea de tiempo is not the active tab. */
  window.addEventListener('scroll', function () {
    if (!lineatiempoActive()) return;
    var anchors = getMonthAnchors();
    if (!anchors.length) { lt2SavedMonth = null; return; }
    var y = window.scrollY + SCROLL_TRACK_OFFSET;
    var saved = null;
    for (var i = 0; i < anchors.length; i++) {
      if (anchors[i].docTop <= y) saved = anchors[i].label;
      else break;
    }
    lt2SavedMonth = saved;
  }, { passive: true });

  /* Restore: called from index.html onTabClick AFTER window.renderLineaTiempo
   * (renderLineaTiempo returns early on cache hits, so this must be a
   * separate call). Restoring re-triggers the scroll listener, which simply
   * re-records the same month. */
  window.restoreLineaTiempoScroll = function () {
    if (!lineatiempoActive()) return;
    if (!lt2Events || !lt2Events.length) return;
    if (!lt2SavedMonth) return;
    var anchors = getMonthAnchors();
    for (var i = 0; i < anchors.length; i++) {
      if (anchors[i].label === lt2SavedMonth) {
        window.scrollTo({ top: Math.max(0, anchors[i].docTop - SCROLL_RESTORE_OFFSET) });
        return;
      }
    }
  };

  /* ------------------------------------------------------------------ */
  /* CSS — injected once, class prefix lt2- (no clash with .tl-*).       */
  /* ------------------------------------------------------------------ */

  function ensureStyles() {
    if (document.getElementById('lt2-styles')) return;
    var css = ''
      + '.lt2-scroller { overflow-x: auto; padding-bottom: 8px; }'
      + '.lt2-table { display: flex; flex-direction: column; width: max-content; margin: 0 auto; }'
      + '.lt2-headrow { display: flex; flex-direction: row; }'
      + '.lt2-gutter-spacer { width: ' + GUTTER_W + 'px; flex: none; }'
      + '.lt2-comp { width: ' + GUTTER_W + 'px; flex: none; }'
      + '.lt2-colhead { width: ' + COL_STEP + 'px; flex: none; padding-right: ' + COL_GAP + 'px; box-sizing: border-box; }'
      + '.lt2-colhead-inner { display: flex; align-items: center; gap: 6px; min-height: 28px;'
      + '  padding: 4px 6px; border: 1px solid #e2e8f0; border-radius: 6px; background: #fff; }'
      + '.lt2-colhead-swatch { width: 10px; height: 10px; border-radius: 3px; flex: none; }'
      + '.lt2-colhead-label { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden;'
      + '  text-overflow: ellipsis; }'
      + '.lt2-body { display: flex; flex-direction: row; align-items: stretch; }'
      + '.lt2-gutter { width: ' + GUTTER_W + 'px; flex: none; position: relative; }'
      + '.lt2-month-label { position: absolute; left: 0; width: ' + (GUTTER_W - 8) + 'px;'
      + '  font-size: 11px; font-weight: 600; color: #475569; white-space: nowrap;'
      + '  font-variant-numeric: tabular-nums; }'
      + '.lt2-canvas { position: relative; }'
      + '.lt2-month-line { position: absolute; left: 0; right: 0; height: 1px; background: #e8edf3; }'
      + '.lt2-col { position: absolute; top: 0; bottom: 0; width: ' + EVENT_W + 'px;'
      + '  background: #f8fafc; border: 1px solid #e8edf3; border-radius: 6px; }'
      + '.lt2-event { position: absolute; left: 0; width: ' + EVENT_W + 'px; height: ' + EVENT_H + 'px;'
      + '  box-sizing: border-box; border-radius: 6px; background: #fff; cursor: pointer;'
      + '  display: flex; align-items: center; justify-content: center; padding: 6px;'
      + '  text-align: center; overflow: hidden; }'
      + '.lt2-event:hover { background: #f8fafc; }'
      + '.lt2-event-text { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;'
      + '  overflow: hidden; text-overflow: ellipsis; font-size: 12px; line-height: 1.3;'
      + '  color: #1e293b; max-height: 100%; }'
      + '.lt2-event-when { position: absolute; top: 4px; left: 0; right: 0; text-align: center;'
      + '  font-size: 10px; font-weight: 600; color: #cbd5e1; letter-spacing: 0.02em;'
      + '  font-variant-numeric: tabular-nums; pointer-events: none; user-select: none; }'
      + '.lt2-undated { margin-top: 20px; box-sizing: border-box; overflow-wrap: anywhere; }'
      + '.lt2-undated h3 { font-size: 14px; font-weight: 600; color: #1e293b; margin: 0 0 8px 0; }'
      + '.lt2-undated-item { display: inline-flex; align-items: center; gap: 6px; margin: 0 8px 6px 0;'
      + '  padding: 4px 10px; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 13px;'
      + '  color: #1e293b; cursor: pointer; background: #fff; }'
      + '.lt2-undated-item:hover { background: #f1f5f9; }'
      + '.lt2-undated-item .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }'
      + '.lt2-empty { padding: 32px; text-align: center; color: #64748b; font-size: 14px; }';
    var style = document.createElement('style');
    style.id = 'lt2-styles';
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ------------------------------------------------------------------ */
  /* Data                                                                */
  /* ------------------------------------------------------------------ */

  function rgb(index) {
    var c = TABLEAU20[index % TABLEAU20.length];
    return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
  }

  function hashModel(model) {
    /* Stable string hash → palette fallback for models without a DB color. */
    var h = 0;
    for (var i = 0; i < model.length; i++) {
      h = ((h * 31) + model.charCodeAt(i)) & 0x7fffffff;
    }
    return h;
  }

  function colorFor(model) {
    var idx = lt2ColorIndex ? lt2ColorIndex[model] : undefined;
    if (idx === undefined || idx === null) idx = hashModel(model) % TABLEAU20.length;
    return rgb(idx);
  }

  async function fetchColors() {
    var res = await fetchWithC('/events/colors');
    if (!res.ok) throw new Error('Error al cargar colores de modelos');
    var data = await res.json();
    var map = {};
    (data.colors || []).forEach(function (item) {
      if (!item || !item.model) return;
      if (item.color_index !== null && item.color_index !== undefined) {
        map[item.model] = item.color_index;
      } else if (!(item.model in map)) {
        map[item.model] = null;
      }
    });
    return map;
  }

  async function fetchAllEvents() {
    var all = [];
    var page = 1;
    var pages = 1;
    while (page <= pages) {
      var res = await fetchWithC('/events?page=' + page + '&per_page=100&sort=time_start&order=asc');
      if (!res.ok) {
        var detail = 'Error al cargar eventos';
        try {
          var errData = await res.json();
          if (errData && errData.detail) detail = errData.detail;
        } catch (_pe) { /* ignore parse error */ }
        throw new Error(detail);
      }
      var data = await res.json();
      pages = data.pages || 0;
      all = all.concat(data.items || []);
      page += 1;
      if (pages === 0) break;
    }
    return all;
  }

  /* ------------------------------------------------------------------ */
  /* Render                                                              */
  /* ------------------------------------------------------------------ */

  function daysInMonth(year, month) {
    return new Date(year, month + 1, 0).getDate();
  }

  function modelKey(item) {
    return (item && item.model) ? String(item.model) : '(sin modelo)';
  }

  function eventText(item) {
    return item.title || truncateText(item.description || '', 140) || '(sin título)';
  }

  function eventTooltip(item) {
    var when = item.time_start
      ? String(item.time_start).replace('T', ' ').slice(0, 16)
      : 'Sin fecha';
    return when + ' — ' + (item.description || item.title || '');
  }

  /* Background watermark for the event card: 3-letter Spanish weekday, day
   * number and hour if present — e.g. "Dom 6 18:00". Shown light grey at
   * the top center so it reads as part of the card background. */
  function eventWhenBg(item) {
    if (!item.time_start) return '';
    var d = new Date(item.time_start);
    if (isNaN(d.getTime())) return '';
    var label = DAYS3[d.getDay()] + ' ' + d.getDate();
    var t = String(item.time_start).match(/T(\d{2}:\d{2})/);
    if (t && t[1] !== '00:00') label += ' ' + t[1];
    return label;
  }

  /* Position events of one month inside one model column.
   *
   * Day-centered with a downward collision pass, plus a remaining-space
   * guarantee: when placing item i, the space left below it must fit all
   * remaining items (each EVENT_H + EVENT_GAP). If it doesn't, the item is
   * shifted up. A final backward cascade then raises earlier items whose
   * positions would overlap a shifted later one (the "previous should have
   * started higher" border case). */
  function layoutMonthEvents(events, monthHeight) {
    var contentHeight = monthHeight - MONTH_PAD * 2;
    var n = events.length;
    var ys = new Array(n);
    var prevBottom = MONTH_PAD - (EVENT_H + EVENT_GAP);
    for (var i = 0; i < n; i++) {
      var item = events[i];
      var d = new Date(item.time_start);
      var dim = daysInMonth(d.getFullYear(), d.getMonth());
      var dayFrac = dim <= 1 ? 0 : (d.getDate() - 1) / (dim - 1);
      var y = MONTH_PAD + dayFrac * (contentHeight - EVENT_H);
      /* Downward collision pass: keep ≥ EVENT_GAP between same-column rects. */
      var minY = prevBottom + EVENT_GAP;
      if (y < minY) y = minY;
      /* Remaining-space check: the space below must fit all remaining items. */
      var remaining = n - 1 - i;
      var maxY = monthHeight - EVENT_H - remaining * (EVENT_H + EVENT_GAP);
      if (y > maxY) y = maxY;
      if (y < MONTH_PAD) y = MONTH_PAD;
      prevBottom = y + EVENT_H;
      ys[i] = y;
    }
    /* Backward cascade: shift earlier items up so nothing overlaps a later
     * item that was pulled up by the remaining-space clamp. */
    for (var j = n - 2; j >= 0; j--) {
      var ceiling = ys[j + 1] - (EVENT_H + EVENT_GAP);
      if (ys[j] > ceiling) ys[j] = ceiling;
    }
    var positioned = [];
    for (var k = 0; k < n; k++) positioned.push({ item: events[k], y: ys[k] });
    return positioned;
  }

  function render(container) {
    ensureStyles();

    var dated = [];
    var undated = [];
    lt2Events.forEach(function (item) {
      if (item.time_start) dated.push(item);
      else undated.push(item);
    });

    /* Distinct models present in the data, sorted by DB index then name. */
    var seen = {};
    var models = [];
    dated.concat(undated).forEach(function (item) {
      var k = modelKey(item);
      if (!seen[k]) { seen[k] = true; models.push(k); }
    });
    models.sort(function (a, b) {
      var ia = lt2ColorIndex && lt2ColorIndex[a] !== undefined ? lt2ColorIndex[a] : null;
      var ib = lt2ColorIndex && lt2ColorIndex[b] !== undefined ? lt2ColorIndex[b] : null;
      var ka = ia === null ? 99 : ia;
      var kb = ib === null ? 99 : ib;
      if (ka !== kb) return ka - kb;
      return a < b ? -1 : (a > b ? 1 : 0);
    });

    /* Bucket dated events by month (local date), then per model column. */
    var monthMap = {};   /* 'y-m' -> { year, month, cols: {model -> [items]}, maxN } */
    var monthKeys = [];
    dated.forEach(function (item) {
      var d = new Date(item.time_start);
      var key = d.getFullYear() + '-' + d.getMonth();
      if (!monthMap[key]) {
        monthMap[key] = { year: d.getFullYear(), month: d.getMonth(), cols: {}, maxN: 0 };
        monthKeys.push(key);
      }
      var k = modelKey(item);
      if (!monthMap[key].cols[k]) monthMap[key].cols[k] = [];
      monthMap[key].cols[k].push(item);
      if (monthMap[key].cols[k].length > monthMap[key].maxN) {
        monthMap[key].maxN = monthMap[key].cols[k].length;
      }
    });
    monthKeys.sort(function (a, b) {
      var pa = a.split('-');
      var pb = b.split('-');
      return (parseInt(pa[0], 10) - parseInt(pb[0], 10))
        || (parseInt(pa[1], 10) - parseInt(pb[1], 10));
    });

    /* Month heights: n = max events of any single model in the month. */
    var monthHeight = {};
    var totalHeight = 0;
    var monthTop = {};   /* key -> y offset of month top within canvas */
    monthKeys.forEach(function (key) {
      var n = monthMap[key].maxN;
      monthHeight[key] = Math.max(1, n) * (EVENT_H + EVENT_GAP) + MONTH_PAD;
      monthTop[key] = totalHeight;
      totalHeight += monthHeight[key];
    });
    if (totalHeight === 0) totalHeight = MONTH_PAD * 2;

    /* Header row: gutter spacer + one header cell per model + compensation. */
    var html = '<div class="lt2-scroller"><div class="lt2-table">';
    html += '<div class="lt2-headrow"><div class="lt2-gutter-spacer"></div>';
    models.forEach(function (m) {
      var c = colorFor(m);
      html += '<div class="lt2-colhead"><div class="lt2-colhead-inner">'
        + '<span class="lt2-colhead-swatch" style="background:' + c + '"></span>'
        + '<span class="lt2-colhead-label" style="color:' + c + '" title="' + escapeHtml(m) + '">'
        + escapeHtml(m) + '</span></div></div>';
    });
    html += '<div class="lt2-comp"></div></div>';

    /* Body: left gutter (month labels) + canvas (columns + rects) + comp. */
    html += '<div class="lt2-body">';
    html += '<div class="lt2-gutter">';
    monthKeys.forEach(function (key) {
      var m = monthMap[key];
      var label = MONTHS3[m.month] + ' ' + m.year;
      html += '<div class="lt2-month-label" style="top:' + (monthTop[key] + MONTH_PAD) + 'px">'
        + escapeHtml(label) + '</div>';
    });
    html += '</div>';

    var canvasW = models.length * COL_STEP - COL_GAP;
    html += '<div class="lt2-canvas" style="width:' + canvasW + 'px;height:' + totalHeight + 'px">';

    /* Month divider lines across all columns. */
    monthKeys.forEach(function (key) {
      html += '<div class="lt2-month-line" style="top:' + monthTop[key] + 'px"></div>';
    });
    /* Bottom closing line. */
    html += '<div class="lt2-month-line" style="top:' + totalHeight + 'px"></div>';

    models.forEach(function (m, mi) {
      var c = colorFor(m);
      html += '<div class="lt2-col" style="left:' + (mi * COL_STEP) + 'px"></div>';
      monthKeys.forEach(function (key) {
        var items = monthMap[key].cols[m];
        if (!items || !items.length) return;
        items.sort(function (a, b) {
          return String(a.time_start).localeCompare(String(b.time_start));
        });
        layoutMonthEvents(items, monthHeight[key]).forEach(function (p) {
          html += '<div class="lt2-event" data-event-id="' + escapeHtml(p.item.event_id) + '"'
            + ' style="left:' + (mi * COL_STEP) + 'px;top:' + (monthTop[key] + p.y) + 'px;'
            + 'border:2px solid ' + c + '"'
            + ' title="' + escapeHtml(eventTooltip(p.item)) + '">'
            + '<span class="lt2-event-when">' + escapeHtml(eventWhenBg(p.item)) + '</span>'
            + '<span class="lt2-event-text">' + escapeHtml(eventText(p.item)) + '</span></div>';
        });
      });
    });

    html += '</div>'; /* canvas */
    html += '<div class="lt2-comp"></div>';
    html += '</div>'; /* body */

    if (undated.length) {
      /* Width-capped to the timeline (gutter + canvas) so long item lists
       * wrap instead of stretching .lt2-table (width: max-content). */
      html += '<div class="lt2-undated" style="width:' + (GUTTER_W + canvasW) + 'px">'
        + '<h3>Sin fecha (' + undated.length + ')</h3>';
      undated.forEach(function (item) {
        var k = modelKey(item);
        html += '<span class="lt2-undated-item" data-event-id="' + escapeHtml(item.event_id) + '"'
          + ' title="' + escapeHtml(eventTooltip(item)) + '">'
          + '<span class="dot" style="background:' + colorFor(k) + '"></span>'
          + escapeHtml(truncateText(eventText(item), 60)) + '</span>';
      });
      html += '</div>';
    }

    html += '</div></div>';
    container.innerHTML = html;
  }

  async function renderLineaTiempo(force) {
    var container = document.getElementById('lineatiempo-container');
    var loading = document.getElementById('lineatiempo-loading');
    if (!container) return;
    if (lt2Loading) return;
    if (lt2Events && !force) return; /* already loaded — skip refetch on tab entry */

    lt2Loading = true;
    if (loading) loading.style.display = 'block';
    try {
      if (!lt2ColorIndex) {
        try {
          lt2ColorIndex = await fetchColors();
        } catch (colorErr) {
          /* Colors are decorative — render with hash fallback instead of failing. */
          lt2ColorIndex = {};
        }
      }
      lt2Events = await fetchAllEvents();
      if (!lt2Events.length) {
        container.innerHTML = '<div class="lt2-empty">No hay eventos para mostrar.</div>';
        return;
      }
      render(container);
    } catch (err) {
      container.innerHTML = '';
      if (typeof showBanner === 'function') {
        showBanner('Error al cargar la línea de tiempo: ' + err.message, 'error', false);
      }
    } finally {
      lt2Loading = false;
      if (loading) loading.style.display = 'none';
    }
  }

  /* Click-through: rectangles and undated rows open the existing detail view. */
  document.addEventListener('click', function (ev) {
    var target = ev.target;
    while (target && target !== document) {
      if (target.classList && target.classList.contains('lt2-event')) {
        if (typeof showEventDetail === 'function') {
          showEventDetail(target.getAttribute('data-event-id'));
        }
        return;
      }
      if (target.classList && target.classList.contains('lt2-undated-item')) {
        if (typeof showEventDetail === 'function') {
          showEventDetail(target.getAttribute('data-event-id'));
        }
        return;
      }
      target = target.parentNode;
    }
  });

  /* Refresh: clears the caches and refetches. Invoked from index.html's
   * universal nav refresh button (window.refreshLineaTiempo) and from
   * window.restoreLineaTiempoScroll (scroll-month memory on tab re-entry)
   * which onTabClick calls after window.renderLineaTiempo. */
  window.refreshLineaTiempo = function () {
    lt2Events = null;
    lt2ColorIndex = null;
    renderLineaTiempo(true);
  };

  window.renderLineaTiempo = renderLineaTiempo;
})();
