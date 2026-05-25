/**
 * Nexus Dashboard — Agents & Models screen (Layout A).
 *
 * Loads from:
 *   GET /api/agents       — agent list (with filters via query string)
 *   GET /api/models       — proxied from OmniRoute /v1/models (TTL 30s)
 *   GET /api/combos       — proxied from OmniRoute /api/combos
 *   GET /api/session/combo — current OMNIROUTE_COMBO selection
 *   GET /api/agents/pending — staged changes
 *   GET /api/agents/diff  — text diff
 *
 * Mutations:
 *   PUT /api/session/combo {combo: "..."}    — set/clear active combo
 *   PUT /api/agents/<name>/model {model: ...}  — stage a model change
 *   POST /api/agents/apply                   — write all staged changes
 */

(() => {
  const PAGE_SIZE = 25;
  let state = {
    agents: [],
    models: [],
    combos: [],
    pending: {},          // {name: {new_model, staged_at}}
    page: 1,
    filters: { category: "", model: "", overridden: false, q: "" },
    selectedNames: new Set(),
    cost: {},             // {modelId: {input, output}}  — TBD if /api/pricing exists
  };

  // ============================================================
  // DOM refs
  // ============================================================
  const $ = (id) => document.getElementById(id);
  const tbody = $("agents-tbody");
  const banner = $("tenant-banner");

  // ============================================================
  // Helpers
  // ============================================================
  function showBanner(html, kind = "warn") {
    banner.className = "panel";
    banner.innerHTML = `<span class="status-${kind === "warn" ? "warn" : "err"}">●</span> ${html}`;
    banner.classList.remove("hidden");
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function modelOptions(currentValue) {
    // Builds <option>s for the per-row dropdown
    const opts = ['<option value="">(unchanged)</option>',
                  '<option value="default">&lt;default&gt;</option>'];

    if (state.combos.length) {
      opts.push('<optgroup label="Combos">');
      for (const c of state.combos) {
        const slug = `omniroute/${c.slug}`;
        const sel = slug === currentValue ? " selected" : "";
        opts.push(`<option value="${escapeHtml(slug)}"${sel}>${escapeHtml(c.slug)} (combo)</option>`);
      }
      opts.push('</optgroup>');
    }
    if (state.models.length) {
      opts.push('<optgroup label="Models">');
      for (const m of state.models) {
        const sel = m.id === currentValue ? " selected" : "";
        opts.push(`<option value="${escapeHtml(m.id)}"${sel}>${escapeHtml(m.id)}</option>`);
      }
      opts.push('</optgroup>');
    }
    return opts.join("");
  }

  // ============================================================
  // Fetch
  // ============================================================
  async function loadAgents() {
    const params = new URLSearchParams();
    if (state.filters.category)   params.set("category", state.filters.category);
    if (state.filters.model)      params.set("model", state.filters.model);
    if (state.filters.overridden) params.set("overridden", "true");
    if (state.filters.q)          params.set("q", state.filters.q);
    const qs = params.toString();
    const data = await api.get("/api/agents" + (qs ? `?${qs}` : ""));
    state.agents = data.items;

    // Populate filter facets first time only
    const catSel = $("filter-category");
    if (catSel.options.length <= 1) {
      for (const c of data.facets.categories) {
        catSel.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`);
      }
    }
  }

  async function loadModelsAndCombos() {
    try {
      const m = await api.get("/api/models");
      state.models = (m.data || []).filter(x => x && x.id).slice(0, 500);
    } catch (e) {
      showBanner(`Models fetch failed: ${escapeHtml(e.message)}. Tela funciona, dropdown vazio.`);
    }
    try {
      const c = await api.get("/api/combos");
      state.combos = c.data || c.items || [];
    } catch {}
    // Populate model filter
    const modelSel = $("filter-model");
    if (modelSel.options.length <= 2) {
      for (const m of state.models.slice(0, 100)) {
        modelSel.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(m.id)}">${escapeHtml(m.id)}</option>`);
      }
    }
    // Populate combo select (top of page)
    const comboSel = $("combo-select");
    for (const c of state.combos) {
      const exists = Array.from(comboSel.options).some(o => o.value === c.slug);
      if (!exists) {
        comboSel.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(c.slug)}">${escapeHtml(c.slug)}</option>`);
      }
    }
    // Populate bulk dropdown (same items as per-row)
    const bulkSel = $("bulk-select");
    bulkSel.innerHTML = modelOptions(null);
    bulkSel.querySelector('option[value=""]').textContent = "Bulk assign…";
  }

  async function loadSessionCombo() {
    const sc = await api.get("/api/session/combo");
    $("combo-select").value = sc.combo || "";
  }

  async function loadPending() {
    const p = await api.get("/api/agents/pending");
    state.pending = {};
    for (const item of p.items) state.pending[item.agent] = item;
    $("pending-count").textContent = p.total;
    const hasPending = p.total > 0;
    $("preview-diff-btn").disabled = !hasPending;
    $("apply-btn").disabled = !hasPending;
    $("discard-btn").disabled = !hasPending;
  }

  // ============================================================
  // Render
  // ============================================================
  function render() {
    const start = (state.page - 1) * PAGE_SIZE;
    const slice = state.agents.slice(start, start + PAGE_SIZE);

    if (slice.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px">No agents match filters.</td></tr>`;
    } else {
      tbody.innerHTML = slice.map(a => {
        const pending = state.pending[a.name];
        const isChanged = pending !== undefined;
        const newModelVal = pending?.new_model ?? "";
        const checked = state.selectedNames.has(a.name) ? "checked" : "";
        const star = isChanged ? `<span class="star" title="Has pending change">★</span>` : "";
        const currentDisplay = a.model || '<span class="muted">&lt;default&gt;</span>';
        return `
          <tr class="${isChanged ? 'row-changed' : ''}" data-name="${escapeHtml(a.name)}">
            <td><input type="checkbox" class="row-check" ${checked} data-name="${escapeHtml(a.name)}"></td>
            <td><strong>${escapeHtml(a.name)}</strong></td>
            <td><span class="muted">${escapeHtml(a.category)}</span></td>
            <td>${star}${currentDisplay}</td>
            <td>
              <select class="row-model btn" data-name="${escapeHtml(a.name)}">
                ${modelOptions(newModelVal)}
              </select>
            </td>
            <td><span class="muted">—</span></td>
          </tr>
        `;
      }).join("");
    }

    // Pagination
    const totalPages = Math.max(1, Math.ceil(state.agents.length / PAGE_SIZE));
    $("page-display").textContent = `${state.page} / ${totalPages}`;
    $("prev-page").disabled = state.page <= 1;
    $("next-page").disabled = state.page >= totalPages;
    $("pagination-info").textContent =
      `Showing ${start + 1}–${Math.min(start + PAGE_SIZE, state.agents.length)} of ${state.agents.length}`;

    // Wire row events
    tbody.querySelectorAll(".row-check").forEach(cb => cb.addEventListener("change", onRowCheck));
    tbody.querySelectorAll(".row-model").forEach(sel => sel.addEventListener("change", onModelChange));

    renderSelection();
  }

  function renderSelection() {
    $("selected-count").textContent = state.selectedNames.size;
    $("bulk-select").disabled = state.selectedNames.size === 0;
    $("bulk-apply-btn").disabled = state.selectedNames.size === 0 || !$("bulk-select").value;
  }

  // ============================================================
  // Event handlers
  // ============================================================
  function onRowCheck(e) {
    const name = e.target.dataset.name;
    if (e.target.checked) state.selectedNames.add(name);
    else state.selectedNames.delete(name);
    renderSelection();
  }

  async function onModelChange(e) {
    const name = e.target.dataset.name;
    const value = e.target.value;  // "" = revert pending; "default" = remove model:; else = stage
    if (value === "") {
      await api.delete(`/api/agents/${encodeURIComponent(name)}/pending`).catch(() => {});
    } else {
      const newModel = value === "default" ? null : value;
      await api.put(`/api/agents/${encodeURIComponent(name)}/model`, { model: newModel });
    }
    await loadPending();
    render();
  }

  // ============================================================
  // Combo set
  // ============================================================
  $("combo-set-btn").addEventListener("click", async () => {
    const slug = $("combo-select").value || "";
    await api.put("/api/session/combo", { combo: slug || null });
    showBanner(`Active combo set to: <strong>${escapeHtml(slug || "(none)")}</strong>`, "ok");
    setTimeout(() => banner.classList.add("hidden"), 3000);
  });

  // ============================================================
  // Filters
  // ============================================================
  async function reload() {
    await loadAgents();
    await loadPending();
    state.page = 1;
    render();
  }

  $("filter-category").addEventListener("change", (e) => { state.filters.category = e.target.value; reload(); });
  $("filter-model").addEventListener("change",    (e) => { state.filters.model = e.target.value; reload(); });
  $("filter-overridden").addEventListener("change", (e) => { state.filters.overridden = e.target.checked; reload(); });

  let searchTimer;
  $("filter-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.filters.q = e.target.value;
      reload();
    }, 250);
  });

  // ============================================================
  // Pagination
  // ============================================================
  $("prev-page").addEventListener("click", () => { state.page--; render(); });
  $("next-page").addEventListener("click", () => { state.page++; render(); });

  // ============================================================
  // Select-all
  // ============================================================
  $("select-all").addEventListener("change", (e) => {
    state.selectedNames.clear();
    if (e.target.checked) {
      const start = (state.page - 1) * PAGE_SIZE;
      state.agents.slice(start, start + PAGE_SIZE).forEach(a => state.selectedNames.add(a.name));
    }
    tbody.querySelectorAll(".row-check").forEach(cb => { cb.checked = e.target.checked; });
    renderSelection();
  });

  // ============================================================
  // Bulk assign
  // ============================================================
  $("bulk-select").addEventListener("change", renderSelection);

  $("bulk-apply-btn").addEventListener("click", async () => {
    const value = $("bulk-select").value;
    if (!value) return;
    const newModel = value === "default" ? null : value;
    for (const name of state.selectedNames) {
      await api.put(`/api/agents/${encodeURIComponent(name)}/model`, { model: newModel });
    }
    await loadPending();
    render();
  });

  // ============================================================
  // Diff modal
  // ============================================================
  $("preview-diff-btn").addEventListener("click", async () => {
    const text = await api.get("/api/agents/diff");
    const html = text.split("\n").map(line => {
      const safe = escapeHtml(line);
      if (line.startsWith("+++") || line.startsWith("---")) return `<span class="diff-meta">${safe}</span>`;
      if (line.startsWith("+")) return `<span class="diff-add">${safe}</span>`;
      if (line.startsWith("-")) return `<span class="diff-del">${safe}</span>`;
      return safe;
    }).join("\n");
    $("diff-content").innerHTML = html;
    $("diff-modal").classList.remove("hidden");
  });

  $("diff-close-btn").addEventListener("click", () => $("diff-modal").classList.add("hidden"));
  $("diff-cancel-btn").addEventListener("click", () => $("diff-modal").classList.add("hidden"));

  $("diff-apply-btn").addEventListener("click", async () => {
    const r = await api.post("/api/agents/apply");
    $("diff-modal").classList.add("hidden");
    showBanner(`Applied ${r.applied} change(s). Files: ${r.files.join(", ")}`, "ok");
    setTimeout(() => banner.classList.add("hidden"), 5000);
    await reload();
  });

  // ============================================================
  // Discard
  // ============================================================
  $("discard-btn").addEventListener("click", async () => {
    if (!confirm("Discard all pending changes?")) return;
    for (const name of Object.keys(state.pending)) {
      await api.delete(`/api/agents/${encodeURIComponent(name)}/pending`).catch(() => {});
    }
    await reload();
  });

  $("apply-btn").addEventListener("click", () => $("preview-diff-btn").click());

  // ============================================================
  // Init
  // ============================================================
  (async () => {
    try {
      await loadModelsAndCombos();
      await loadSessionCombo();
      await reload();
    } catch (e) {
      console.error(e);
      showBanner(`Init failed: ${escapeHtml(e.message)}`, "err");
    }
  })();
})();
