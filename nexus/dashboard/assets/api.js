/**
 * Minimal typed client for Nexus Dashboard's local API.
 * All calls are loopback (localhost:8081), no auth.
 *
 * Usage:
 *   const data = await api.get("/api/agents");
 *   await api.put("/api/agents/reviewer-1/model", { model: "omniroute/claude-opus-4-7" });
 */

window.api = {
  _request: function(method, path, body) {
    if (body === undefined) { body = null; }
    var opts = { method: method, headers: { "Accept": "application/json" } };
    if (body !== null) {
      opts.body = JSON.stringify(body);
      opts.headers["Content-Type"] = "application/json";
    }
    return fetch(path, opts).then(function(resp) {
      var ct = resp.headers.get("Content-Type") || "";
      var dataPromise = ct.indexOf("application/json") !== -1
        ? resp.json()
        : resp.text();
      return dataPromise.then(function(data) {
        if (!resp.ok) {
          var msg = data && data.error ? data.error : "HTTP " + resp.status;
          var err = new Error(msg);
          err.status = resp.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  },

  get: function(path) { return this._request("GET", path); },
  put: function(path, body) { return this._request("PUT", path, body); },
  post: function(path, body) { return this._request("POST", path, body); },
  delete: function(path) { return this._request("DELETE", path); },

  /** Simple SSE subscriber for streaming API endpoints (e.g. /api/x/stream). */
  stream: function(path, onEvent, onError) {
    var es = new EventSource(path);
    es.onmessage = function(evt) {
      try { onEvent(JSON.parse(evt.data)); }
      catch (e) { onEvent(evt.data); }
    };
    es.onerror = function(e) { if (onError) { onError(e); } };
    return es; // caller can .close()
  },
};
