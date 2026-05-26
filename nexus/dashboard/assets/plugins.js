/**
 * Nexus Dashboard — Plugins screen (Layout A).
 */

(() => {
  let state = {
    plugins: [],
    pending: {},
    expanded: new Set(),  // plugin ids
    filterQ: "",
    hasComments: false,
  };

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

  // Guard against prototype pollution — reject dangerous key segments.
  const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);
  function isSafeKey(k) { return typeof k === "string" && !UNSAFE_KEYS.has(k); }

  // Safe own-property read: never traverses the prototype chain.
  function safeGet(o, k) {
    if (!o || typeof o !== "object") return undefined;
    if (!Object.prototype.hasOwnProperty.call(o, k)) return undefined;
    return o[k];
  }

  // Get nested value: getNested(obj, "features.combos")
  function getNested(obj, path) {
    const parts = path.split(".");
    let cur = obj;
    for (const p of parts) {
      if (!isSafeKey(p) || cur === null || typeof cur !== "object") return undefined;
      cur = Object.prototype.hasOwnProperty.call(cur, p) ? Object.getOwnPropertyDescriptor(cur, p).value : undefined;
    }
    return cur;
  }

  function setNested(obj, path, value) {
    const parts = path.split(".");
    let cur = obj;
    for (let i = 0; i < parts.length - 1; i++) {
      const k = parts[i];
      if (!isSafeKey(k)) return;
      if (!Object.prototype.hasOwnProperty.call(cur, k) || typeof Object.getOwnPropertyDescriptor(cur, k).value !== "object") {
        Object.defineProperty(cur, k, { value: Object.create(null), writable: true, enumerable: true, configurable: true });
      }
      cur = Object.getOwnPropertyDescriptor(cur, k).value;
    }
    const last = parts[parts.length - 1];
    if (isSafeKey(last)) {
      Object.defineProperty(cur, last, { value, writable: true, enumerable: true, configurable: true });
    }
  }

  // ============================================================
  // Loaders
  // ============================================================
  async function loadPlugins() {
    const data = await api.get("/api/plugins");
    state.plugins = data.plugins;
    state.hasComments = data.has_comments;
    if (data.config_warning) {
      $("comments-banner").className = "panel";
      $("comments-banner").innerHTML = `<span class="status-warn">⚠</span> ${escapeHtml(data.config_warning)}`;
      $("comments-banner").classList.remove("hidden");
    } else {
      $("comments-banner").classList.add("hidden");
    }
  }

  async function loadPending() {
    const data = await api.get("/api/plugins/pending");
    state.pending = data.items || {};
    $("pending-count").textContent = data.total;
    const hasPending = data.total > 0;
    $("preview-diff-btn").disabled = !hasPending;
    $("apply-btn").disabled = !hasPending;
    $("discard-btn").disabled = !hasPending;
  }

  // ============================================================
  // Render
  // ============================================================
  function render() {
    let items = [...state.plugins];
    if (state.filterQ) {
      const q = state.filterQ.toLowerCase();
      items = items.filter(p => p.name.toLowerCase().includes(q) || p.id.toLowerCase().includes(q));
    }

    const tbody = $("plugins-tbody");
    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">No plugins match.</td></tr>`;
      return;
    }

    let html = "";
    for (const p of items) {
      const isPending = state.pending[p.id] !== undefined;
      const isExpanded = state.expanded.has(p.id);
      const pendingChange = state.pending[p.id];
      const enabled = pendingChange ? pendingChange.enabled : p.enabled;

      const optsCell = p.schema && p.schema.options.length > 0
        ? `<button class="btn cfg-btn" data-id="${escapeHtml(p.id)}">${isExpanded ? "▲ Collapse" : "▼ Configure"}</button>`
        : `<span class="muted">no options</span>`;

      html += `
        <tr class="${isPending ? "row-changed" : ""} ${isExpanded ? "row-expanded" : ""}" data-id="${escapeHtml(p.id)}">
          <td><span class="toggle ${enabled ? "on" : ""}" data-id="${escapeHtml(p.id)}"><span class="knob"></span></span></td>
          <td>
            <strong>${escapeHtml(p.name)}</strong>
            ${isPending ? " <small class=\"status-warn\">★ pending</small>" : ""}
            <div class="muted" style="font-size:11px">${escapeHtml(p.id)}</div>
          </td>
          <td class="mono">${escapeHtml(p.version || "—")}</td>
          <td><span class="status-ok">●</span> ${escapeHtml(enabled ? "active" : "disabled")}</td>
          <td>${optsCell}</td>
        </tr>
      `;

      if (isExpanded && p.schema && p.schema.options.length > 0) {
        const currentOpts = pendingChange?.options ?? p.options ?? {};
        html += `
          <tr class="opts-row">
            <td colspan="5">
              <div class="options-form" data-id="${escapeHtml(p.id)}">
                ${renderOptionsForm(p, currentOpts)}
                <div class="flex" style="margin-top:12px">
                  <button class="btn primary stage-btn" data-id="${escapeHtml(p.id)}">Stage change</button>
                  <button class="btn reset-btn" data-id="${escapeHtml(p.id)}">Reset</button>
                </div>
              </div>
            </td>
          </tr>
        `;
      }
    }

    tbody.innerHTML = html;

    $("plugin-counts").textContent = `${items.length} plugins · ${Object.keys(state.pending).length} modified`;

    // Wire up events
    tbody.querySelectorAll(".toggle").forEach(t =>
      t.addEventListener("click", () => stageToggle(t.dataset.id, !t.classList.contains("on")))
    );
    tbody.querySelectorAll(".cfg-btn").forEach(b =>
      b.addEventListener("click", () => {
        if (state.expanded.has(b.dataset.id)) state.expanded.delete(b.dataset.id);
        else state.expanded.add(b.dataset.id);
        render();
      })
    );
    tbody.querySelectorAll(".stage-btn").forEach(b =>
      b.addEventListener("click", () => stageOptions(b.dataset.id))
    );
    tbody.querySelectorAll(".reset-btn").forEach(b =>
      b.addEventListener("click", () => resetOptions(b.dataset.id))
    );
  }

  function renderOptionsForm(plugin, currentOpts) {
    const schema = plugin.schema.options;
    const fields = schema.filter(s => !s.name.includes("."));
    const features = schema.filter(s => s.name.startsWith("features."));

    let html = "";
    for (const f of fields) {
      const val = currentOpts[f.name] ?? f.default ?? "";
      html += `
        <div class="field">
          <label>${escapeHtml(f.name)}${f.required ? " <span class=\"status-err\">*</span>" : ""}:</label>
          <input type="${f.type === "integer" ? "number" : "text"}"
                 name="${escapeHtml(f.name)}"
                 value="${escapeHtml(String(val))}"
                 data-plugin="${escapeHtml(plugin.id)}">
          <span class="muted" style="font-size:11px">${escapeHtml(f.type)}</span>
        </div>
      `;
    }

    if (features.length > 0) {
      html += `<div style="margin-top:8px"><strong>Features:</strong></div><div class="features">`;
      for (const f of features) {
        const key = f.name.replace("features.", "");
        const val = getNested(currentOpts, f.name) ?? f.default ?? false;
        html += `
          <label>
            <input type="checkbox"
                   name="${escapeHtml(f.name)}"
                   ${val ? "checked" : ""}
                   data-plugin="${escapeHtml(plugin.id)}">
            <span class="mono" style="font-size:11px">${escapeHtml(key)}</span>
          </label>
        `;
      }
      html += `</div>`;
    }

    return html;
  }

  // ============================================================
  // Mutation actions
  // ============================================================
  async function stageToggle(pluginId, newEnabled) {
    const current = state.plugins.find(p => p.id === pluginId);
    if (!current) return;
    await api.put(`/api/plugins/${encodeURIComponent(pluginId)}`, {
      enabled: newEnabled,
      options: newEnabled ? (state.pending[pluginId]?.options ?? null) : null,
    });
    await loadPending();
    render();
  }

  async function stageOptions(pluginId) {
    const form = document.querySelector(`.options-form[data-id="${CSS.escape(pluginId)}"]`);
    if (!form) return;
    const opts = {};
    form.querySelectorAll("input[name]").forEach(input => {
      const name = input.name;
      let val;
      if (input.type === "checkbox") val = input.checked;
      else if (input.type === "number") val = input.value === "" ? null : Number(input.value);
      else val = input.value;
      if (val !== null && val !== "") setNested(opts, name, val);
    });
    try {
      await api.put(`/api/plugins/${encodeURIComponent(pluginId)}`, {
        enabled: true,
        options: opts,
      });
      await loadPending();
      render();
    } catch (e) {
      alert(`Stage failed: ${e.message}`);
    }
  }

  async function resetOptions(pluginId) {
    await api.delete(`/api/plugins/${encodeURIComponent(pluginId)}/pending`).catch(() => {});
    await loadPending();
    render();
  }

  // ============================================================
  // Diff modal + apply
  // ============================================================
  $("preview-diff-btn").addEventListener("click", async () => {
    const diff = await api.get("/api/plugins/diff");
    const html = diff.split("\n").map(line => {
      const safe = escapeHtml(line);
      if (line.startsWith("+++") || line.startsWith("---")) return `<span class="diff-meta">${safe}</span>`;
      if (line.startsWith("+")) return `<span class="diff-add">${safe}</span>`;
      if (line.startsWith("-")) return `<span class="diff-del">${safe}</span>`;
      return safe;
    }).join("\n");
    $("diff-content").innerHTML = html;
    $("diff-warning").classList.toggle("hidden", !state.hasComments);
    $("diff-modal").classList.remove("hidden");
  });

  $("diff-close-btn").addEventListener("click", () => $("diff-modal").classList.add("hidden"));
  $("diff-cancel-btn").addEventListener("click", () => $("diff-modal").classList.add("hidden"));

  $("diff-apply-btn").addEventListener("click", async () => {
    try {
      const r = await api.post("/api/plugins/apply");
      $("diff-modal").classList.add("hidden");
      alert(`Applied ${r.applied} change(s). Backup: ${r.backup}\n\n${r.restart_hint}`);
      await loadPlugins();
      await loadPending();
      render();
    } catch (e) {
      alert(`Apply failed: ${e.message}`);
    }
  });

  $("apply-btn").addEventListener("click", () => $("preview-diff-btn").click());

  $("discard-btn").addEventListener("click", async () => {
    if (!confirm("Discard all pending plugin changes?")) return;
    for (const id of Object.keys(state.pending)) {
      await api.delete(`/api/plugins/${encodeURIComponent(id)}/pending`).catch(() => {});
    }
    await loadPending();
    render();
  });

  // ============================================================
  // Restart info modal
  // ============================================================
  $("how-restart-btn").addEventListener("click", () => $("restart-modal").classList.remove("hidden"));
  $("restart-close-btn").addEventListener("click", () => $("restart-modal").classList.add("hidden"));

  // ============================================================
  // Filters
  // ============================================================
  let searchTimer;
  $("filter-search").addEventListener("input", e => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.filterQ = e.target.value; render(); }, 200);
  });

  // ============================================================
  // Init
  // ============================================================
  (async () => {
    try {
      await loadPlugins();
      await loadPending();
      render();
    } catch (e) {
      console.error(e);
      $("plugins-tbody").innerHTML = `<tr><td colspan="5" class="status-err" style="text-align:center;padding:24px">Init failed: ${escapeHtml(e.message)}</td></tr>`;
    }
  })();
})();
