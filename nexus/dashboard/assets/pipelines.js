/**
 * Nexus Dashboard — Pipelines screen (Layout C).
 *
 * - Tab Commands: lista comandos com Run button → modal com form de args
 * - Tab Runs: lista runs com drawer inferior; SSE para stream de output
 */

(() => {
  const POLL_RUNS_MS = 5000;

  let state = {
    activeTab: "commands",
    commands: [],
    runs: [],
    selectedRunId: null,
    cmdFilters: { category: "", q: "" },
    runsFilters: { status: "" },
    sse: null,
  };

  const $ = (id) => document.getElementById(id);
  const escapeHtml = (s) => String(s ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));

  // ============================================================
  // Tabs
  // ============================================================
  function switchTab(tabKey) {
    state.activeTab = tabKey;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tabKey));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("hidden", p.dataset.pane !== tabKey));
  }
  document.querySelectorAll(".tab-btn").forEach(b =>
    b.addEventListener("click", () => switchTab(b.dataset.tab))
  );

  // ============================================================
  // Commands
  // ============================================================
  async function loadCommands() {
    const data = await api.get("/api/pipelines");
    state.commands = data.items;
    $("cmd-count").textContent = data.total;

    const catSel = $("cmd-filter-category");
    if (catSel.options.length <= 1) {
      for (const c of (data.categories || [])) {
        catSel.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`);
      }
    }
    renderCommands();
  }

  function renderCommands() {
    let items = [...state.commands];
    if (state.cmdFilters.category) items = items.filter(c => (c.category || "uncategorized") === state.cmdFilters.category);
    if (state.cmdFilters.q) {
      const q = state.cmdFilters.q.toLowerCase();
      items = items.filter(c => c.name.toLowerCase().includes(q));
    }

    const tbody = $("commands-tbody");
    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted" style="text-align:center;padding:24px">No commands match filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(c => {
      const argsSummary = (c.arguments || []).map(a =>
        `<code>${escapeHtml(a.name)}${a.required ? "*" : ""}</code>`
      ).join(", ") || '<span class="muted">none</span>';
      return `
        <tr data-cmd="${escapeHtml(c.name)}">
          <td class="muted">${escapeHtml(c.category || "uncat")}</td>
          <td><strong>/${escapeHtml(c.name)}</strong></td>
          <td>${escapeHtml(c.description || "")}</td>
          <td>${argsSummary}</td>
          <td><button class="btn primary cmd-run-btn" data-cmd="${escapeHtml(c.name)}">▶ Run</button></td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll(".cmd-run-btn").forEach(btn =>
      btn.addEventListener("click", e => {
        e.stopPropagation();
        openRunModal(btn.dataset.cmd);
      })
    );
  }

  $("cmd-filter-category").addEventListener("change", e => { state.cmdFilters.category = e.target.value; renderCommands(); });
  $("cmd-filter-search").addEventListener("input", e => {
    state.cmdFilters.q = e.target.value;
    renderCommands();
  });

  // ============================================================
  // Run modal
  // ============================================================
  function openRunModal(cmdName) {
    const cmd = state.commands.find(c => c.name === cmdName);
    if (!cmd) return;

    $("modal-cmd-name").textContent = `/${cmd.name}`;
    $("modal-cmd-desc").textContent = cmd.description || "";

    const fields = (cmd.arguments || []).map(a => `
      <div class="field">
        <label>
          ${escapeHtml(a.name)}${a.required ? '<span class="required"> *</span>' : ""}
          <small class="muted">(${escapeHtml(a.type)})</small>
        </label>
        ${a.type === "boolean"
          ? `<select name="${escapeHtml(a.name)}"><option value="false">false</option><option value="true">true</option></select>`
          : `<input name="${escapeHtml(a.name)}" type="${a.type === "integer" ? "number" : "text"}" ${a.required ? "required" : ""}>`
        }
        ${a.description ? `<div class="desc">${escapeHtml(a.description)}</div>` : ""}
      </div>
    `).join("");

    $("modal-args-fields").innerHTML = fields || '<div class="muted">No arguments required.</div>';
    $("modal-error").classList.add("hidden");
    $("run-modal").classList.remove("hidden");
    $("run-form").dataset.cmd = cmd.name;
  }

  function closeRunModal() { $("run-modal").classList.add("hidden"); }
  $("modal-close").addEventListener("click", closeRunModal);
  $("modal-cancel").addEventListener("click", closeRunModal);

  $("run-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const cmd = e.target.dataset.cmd;
    const formData = new FormData(e.target);
    const args = {};
    for (const [k, v] of formData.entries()) {
      if (v !== "") args[k] = v;
    }
    try {
      const resp = await api.post("/api/pipelines/run", {
        command: `/${cmd}`,
        args,
      });
      closeRunModal();
      switchTab("runs");
      state.selectedRunId = resp.run_id;
      await loadRuns();
      openDrawer(resp.run_id);
    } catch (err) {
      $("modal-error").classList.remove("hidden");
      $("modal-error").textContent = err.message;
    }
  });

  // ============================================================
  // Runs
  // ============================================================
  async function loadRuns() {
    const data = await api.get("/api/pipelines/runs");
    state.runs = data.items;
    $("runs-count").textContent = data.summary.total;
    $("running-count").textContent = `${data.summary.running} running`;
    $("running-count").classList.toggle("status-warn", data.summary.running > 0);
    $("running-count").classList.toggle("status-ok",   data.summary.running === 0);
    $("runs-summary").textContent =
      `${data.summary.running} running · ${data.summary.ok} ok · ${data.summary.failed} failed · ${data.summary.cancelled} cancelled`;
    renderRuns();
  }

  function fmtDuration(meta) {
    const start = meta.started_at ? new Date(meta.started_at) : null;
    const end   = meta.finished_at ? new Date(meta.finished_at) : new Date();
    if (!start) return "—";
    const ms = end - start;
    if (isNaN(ms) || ms < 0) return "—";
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;
  }

  function fmtRelative(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    if (ms < 60_000) return `${Math.round(ms/1000)}s ago`;
    if (ms < 3_600_000) return `${Math.round(ms/60_000)}m ago`;
    if (ms < 86_400_000) return `${Math.round(ms/3_600_000)}h ago`;
    return `${Math.round(ms/86_400_000)}d ago`;
  }

  const STATUS_DOT = {
    running: "●", ok: "✓", failed: "✗", cancelled: "■", timeout: "⏱", orphan: "?",
  };

  function renderRuns() {
    let items = [...state.runs];
    if (state.runsFilters.status) items = items.filter(r => r.status === state.runsFilters.status);

    const tbody = $("runs-tbody");
    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px">No runs match filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(r => {
      const sel = r.run_id === state.selectedRunId ? " selected" : "";
      const dot = STATUS_DOT[r.status] || "?";
      const argsStr = r.args && Object.keys(r.args).length ? JSON.stringify(r.args) : "—";
      return `
        <tr class="status-${r.status}${sel}" data-runid="${escapeHtml(r.run_id)}">
          <td><span class="status-dot">${dot}</span> ${r.status.toUpperCase()}</td>
          <td>${escapeHtml(r.command)}</td>
          <td>${escapeHtml(argsStr)}</td>
          <td class="muted">${fmtRelative(r.started_at)}</td>
          <td>${fmtDuration(r)}</td>
          <td class="muted">${r.pid || "—"}</td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll("tr[data-runid]").forEach(tr =>
      tr.addEventListener("click", () => openDrawer(tr.dataset.runid))
    );
  }

  $("runs-filter-status").addEventListener("change", e => { state.runsFilters.status = e.target.value; renderRuns(); });

  // ============================================================
  // Drawer + SSE
  // ============================================================
  function openDrawer(runId) {
    state.selectedRunId = runId;
    const run = state.runs.find(r => r.run_id === runId);
    if (!run) return;

    $("drawer-title").textContent = `${run.command}  (${run.status})`;
    $("drawer-meta").textContent  = `run_id: ${run.run_id} · pid: ${run.pid || "—"} · started ${fmtRelative(run.started_at)} · ${fmtDuration(run)}`;
    $("drawer-terminal").textContent = "";
    $("drawer-cancel").classList.toggle("hidden", run.status !== "running");
    $("run-drawer").classList.remove("hidden");
    renderRuns();

    if (state.sse) { state.sse.close(); state.sse = null; }

    state.sse = new EventSource(`/api/pipelines/runs/${encodeURIComponent(runId)}/output/stream`);
    state.sse.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.line !== undefined) {
          $("drawer-terminal").textContent += data.line + "\n";
          $("drawer-terminal").scrollTop = $("drawer-terminal").scrollHeight;
        }
      } catch {}
    };
    state.sse.addEventListener("close", () => {
      state.sse.close();
      state.sse = null;
      // Reload runs to update status
      loadRuns();
    });
    state.sse.onerror = () => { /* EventSource auto-reconnect */ };
  }

  $("drawer-close").addEventListener("click", () => {
    $("run-drawer").classList.add("hidden");
    if (state.sse) { state.sse.close(); state.sse = null; }
    state.selectedRunId = null;
    renderRuns();
  });

  $("drawer-cancel").addEventListener("click", async () => {
    if (!state.selectedRunId) return;
    if (!confirm(`Cancel run ${state.selectedRunId}?`)) return;
    try {
      await api.post(`/api/pipelines/runs/${encodeURIComponent(state.selectedRunId)}/cancel`);
      await loadRuns();
    } catch (e) {
      alert(`Cancel failed: ${e.message}`);
    }
  });

  // ============================================================
  // Refresh
  // ============================================================
  $("refresh-btn").addEventListener("click", () => { loadRuns(); loadCommands(); });

  setInterval(() => { loadRuns(); }, POLL_RUNS_MS);

  // ============================================================
  // Init
  // ============================================================
  (async () => {
    try {
      await loadCommands();
      await loadRuns();
    } catch (e) {
      console.error(e);
    }
  })();
})();
