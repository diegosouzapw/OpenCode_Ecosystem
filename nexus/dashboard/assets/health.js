/**
 * Nexus Dashboard — Health screen (Layout B).
 *
 * Subscribes to /api/health/stream (SSE, 5s tick).
 * Renders a unified table of providers + MCPs.
 * Sort/filter client-side. Click row → inline drawer with extra details.
 */

(() => {
  let state = {
    providers: [],
    mcps: [],
    summary: { ok: 0, warn: 0, crit: 0, off: 0, total: 0 },
    lastUpdate: null,
    paused: false,
    filters: { type: "", status: "", problemsOnly: false },
    sortBy: "score-asc",
    selectedName: null,
  };
  let es = null;

  const $ = (id) => document.getElementById(id);

  // ============================================================
  // Helpers
  // ============================================================
  const STATUS_DOT = { ok: "●", warn: "○", crit: "○", off: "○" };
  const STATUS_LABEL = { ok: "OK", warn: "WARN", crit: "CRIT", off: "OFF" };

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function fmtRelative(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    if (ms < 0 || isNaN(ms)) return "—";
    if (ms < 5000) return "just now";
    if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
    if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
    return `${Math.round(ms / 3_600_000)}h ago`;
  }

  function showBanner(html, kind = "warn") {
    const el = $("conn-banner");
    el.className = "panel";
    el.innerHTML = `<span class="status-${kind === "warn" ? "warn" : "err"}">●</span> ${html}`;
    el.classList.remove("hidden");
  }

  function hideBanner() { $("conn-banner").classList.add("hidden"); }

  // ============================================================
  // Filter + sort
  // ============================================================
  function getFiltered() {
    let items = [...state.providers, ...state.mcps];
    const { type, status, problemsOnly } = state.filters;

    if (type) items = items.filter(i => i.type === type);
    if (status) items = items.filter(i => i.status === status);
    if (problemsOnly) items = items.filter(i => i.status !== "ok");

    switch (state.sortBy) {
      case "score-asc":  items.sort((a, b) => a.score - b.score); break;
      case "score-desc": items.sort((a, b) => b.score - a.score); break;
      case "name":       items.sort((a, b) => a.name.localeCompare(b.name)); break;
      case "type":       items.sort((a, b) => a.type.localeCompare(b.type) || a.score - b.score); break;
      case "last_check": items.sort((a, b) => (b.last_check || "").localeCompare(a.last_check || "")); break;
    }
    return items;
  }

  // ============================================================
  // Render
  // ============================================================
  function render() {
    const items = getFiltered();
    const tbody = $("health-tbody");

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px">No items match filters.</td></tr>`;
    } else {
      tbody.innerHTML = items.map(i => {
        const selected = i.name === state.selectedName ? " selected" : "";
        const dot = STATUS_DOT[i.status] || "?";
        const label = STATUS_LABEL[i.status] || i.status.toUpperCase();
        return `
          <tr class="row-${i.status}${selected}" data-name="${escapeHtml(i.name)}" data-type="${i.type}">
            <td class="status-cell"><span class="dot">${dot}</span> ${label}</td>
            <td>${i.type}</td>
            <td><strong>${escapeHtml(i.name)}</strong></td>
            <td>${i.score}</td>
            <td>${escapeHtml(i.details)}</td>
            <td class="muted">${fmtRelative(i.last_check)}</td>
          </tr>
        `;
      }).join("");
      tbody.querySelectorAll("tr[data-name]").forEach(tr => {
        tr.addEventListener("click", () => showDetail(tr.dataset.name, tr.dataset.type));
      });
    }

    $("row-count").textContent = `${items.length} of ${state.summary.total} items`;

    // Bottom alerts bar
    const crit = state.providers.concat(state.mcps).filter(x => x.status === "crit");
    const warn = state.providers.concat(state.mcps).filter(x => x.status === "warn");
    const off  = state.providers.concat(state.mcps).filter(x => x.status === "off");

    $("crit-count").textContent = `${crit.length + off.length} CRITICAL/OFF`;
    $("crit-list").textContent = crit.concat(off).map(x => x.name).slice(0, 5).join(", ") +
      (crit.length + off.length > 5 ? `, +${crit.length + off.length - 5}` : "") || "—";

    $("warn-count").textContent = `${warn.length} WARNING`;
    $("warn-list").textContent = warn.map(x => x.name).slice(0, 5).join(", ") +
      (warn.length > 5 ? `, +${warn.length - 5}` : "") || "—";

    $("ok-count").textContent = `${state.summary.ok} OK`;

    $("last-update").textContent = state.lastUpdate ? fmtRelative(state.lastUpdate) : "—";

    // Update detail if selected and still present
    if (state.selectedName) {
      const sel = items.find(i => i.name === state.selectedName);
      if (sel) renderDetail(sel);
    }
  }

  // ============================================================
  // Detail drawer
  // ============================================================
  function showDetail(name, type) {
    state.selectedName = name;
    const item = (type === "prov" ? state.providers : state.mcps).find(x => x.name === name);
    if (!item) return;
    $("detail-drawer").classList.remove("hidden");
    renderDetail(item);
    render(); // to highlight the row
  }

  function renderDetail(item) {
    $("detail-title").innerHTML = `<span class="dot row-${item.status}" style="margin-right:6px">${STATUS_DOT[item.status]}</span> ${escapeHtml(item.name)} <small class="muted">(${item.type})</small>`;
    const extra = item.extra || {};
    const rows = Object.entries(extra).map(([k, v]) =>
      `<div class="conn-row"><strong>${escapeHtml(k)}</strong>: ${escapeHtml(JSON.stringify(v))}</div>`
    ).join("");
    $("detail-content").innerHTML = `
      <div><small class="muted">score:</small> <strong>${item.score}</strong> · <small class="muted">last check:</small> ${escapeHtml(item.last_check || "—")}</div>
      <div style="margin-top:12px"><strong>Extra:</strong></div>
      ${rows || '<div class="muted">no extra fields</div>'}
    `;
  }

  $("detail-close").addEventListener("click", () => {
    state.selectedName = null;
    $("detail-drawer").classList.add("hidden");
    render();
  });

  // ============================================================
  // SSE subscription
  // ============================================================
  function connectStream() {
    if (es) es.close();

    try {
      es = new EventSource("/api/health/stream");
    } catch (e) {
      showBanner(`EventSource not supported: ${escapeHtml(e.message)}`, "err");
      return;
    }

    es.onmessage = (evt) => {
      if (state.paused) return;
      try {
        const data = JSON.parse(evt.data);
        state.providers = data.providers || [];
        state.mcps = data.mcps || [];
        state.summary = data.summary || state.summary;
        state.lastUpdate = data.ts;
        hideBanner();
        render();
      } catch (e) {
        console.error("[health] parse error", e, evt.data);
      }
    };

    es.addEventListener("close", () => {
      // Server signaled end of stream — reconnect after a short delay
      setTimeout(connectStream, 1000);
    });

    es.onerror = () => {
      showBanner("Connection lost. Reconnecting…", "err");
      $("refresh-indicator").textContent = "● reconnecting";
      $("refresh-indicator").classList.add("paused");
      // EventSource auto-reconnects; we don't have to close + reopen
    };

    es.onopen = () => {
      $("refresh-indicator").textContent = "● live";
      $("refresh-indicator").classList.remove("paused");
    };
  }

  // ============================================================
  // Controls
  // ============================================================
  $("pause-btn").addEventListener("click", () => {
    state.paused = !state.paused;
    $("pause-btn").textContent = state.paused ? "Resume" : "Pause";
    $("refresh-indicator").textContent = state.paused ? "● paused" : "● live";
    $("refresh-indicator").classList.toggle("paused", state.paused);
  });

  $("filter-type").addEventListener("change", (e) => { state.filters.type = e.target.value; render(); });
  $("filter-status").addEventListener("change", (e) => { state.filters.status = e.target.value; render(); });
  $("filter-problems").addEventListener("change", (e) => { state.filters.problemsOnly = e.target.checked; render(); });
  $("sort-by").addEventListener("change", (e) => { state.sortBy = e.target.value; render(); });

  $("toggle-problems").addEventListener("click", () => {
    $("filter-problems").checked = !$("filter-problems").checked;
    state.filters.problemsOnly = $("filter-problems").checked;
    render();
  });

  // ============================================================
  // Init
  // ============================================================
  connectStream();
})();
