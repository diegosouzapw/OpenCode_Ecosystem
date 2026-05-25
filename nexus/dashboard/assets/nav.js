/**
 * Shared sidebar navigation for the Nexus Dashboard.
 *
 * Usage in HTML:
 *   <div id="nav"></div>
 *   <script src="/assets/nav.js"></script>
 *   <script>renderNav("agents");</script>  // active item key
 */

window.renderNav = function (activeKey) {
  if (activeKey === undefined) { activeKey = "overview"; }

  var items = [
    { key: "overview",  href: "/",          label: "Overview",        icon: "📊" },
    { key: "agents",    href: "/agents",    label: "Agents & Models", icon: "🤖", since: "PR-7" },
    { key: "health",    href: "/health",    label: "Health",          icon: "🩺", since: "PR-8" },
    { key: "pipelines", href: "/pipelines", label: "Pipelines",       icon: "▶️", since: "PR-9" },
    { key: "plugins",   href: "/plugins",   label: "Plugins",         icon: "🔌", since: "PR-10" },
  ];

  var container = document.getElementById("nav");
  if (!container) {
    console.warn("[nav.js] No #nav element in DOM");
    return;
  }

  var liItems = items.map(function(i) {
    var activeClass = i.key === activeKey ? " active" : "";
    var pendingClass = i.since ? " pending" : "";
    var badge = i.since ? '<span class="badge">' + i.since + '</span>' : "";
    return (
      '<li class="sidebar-item' + activeClass + pendingClass + '">' +
        '<a href="' + i.href + '">' +
          '<span class="icon">' + i.icon + '</span>' +
          '<span class="label">' + i.label + '</span>' +
          badge +
        '</a>' +
      '</li>'
    );
  }).join("");

  container.innerHTML =
    '<nav class="sidebar">' +
      '<div class="sidebar-brand">' +
        '<span class="brand-icon">🧠</span>' +
        '<span class="brand-text">Nexus<br/><small>Dashboard v3</small></span>' +
      '</div>' +
      '<ul class="sidebar-items">' + liItems + '</ul>' +
      '<div class="sidebar-footer">' +
        '<small id="omniroute-status">checking…</small>' +
      '</div>' +
    '</nav>';

  // Best-effort: probe /api/ping and show OmniRoute env status
  fetch("/api/ping")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var el = document.getElementById("omniroute-status");
      if (!el) { return; }
      if (data.omniroute_enabled) {
        el.innerHTML = '<span class="status-ok">●</span> OmniRoute: ' + (data.omniroute_base_url || "configured");
      } else {
        el.innerHTML = '<span class="status-off">●</span> OmniRoute: not configured';
      }
    })
    .catch(function() {
      var el = document.getElementById("omniroute-status");
      if (el) { el.textContent = "ping failed"; }
    });
};
