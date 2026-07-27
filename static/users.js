/*
   users.js
   --------
   Small shared helpers for the Users administration pages (list / create /
   edit / detail). Each page still holds its own page-specific script inline
   (the same style as login.html and dashboard.html); this file only collects
   the bits every page needs so we don't repeat them.

   It builds on Auth (auth.js): Auth.apiFetch attaches the token and redirects
   to /login on a 401. Load auth.js BEFORE this file.
*/

const Users = {
  /**
   * Ask the API which permission codes the logged-in user has, so a page can
   * hide buttons the user isn't allowed to use. Returns a Set of strings.
   * (The server still enforces every permission — this is only for the UI.)
   */
  async fetchMyPermissions() {
    try {
      const response = await Auth.apiFetch("/api/me/permissions");
      if (!response.ok) return new Set();
      const data = await response.json();
      return new Set(data.permissions || []);
    } catch (err) {
      // apiFetch already redirects on a 401; otherwise fail closed (no perms).
      return new Set();
    }
  },

  /** Turn any value into text that is safe to drop into innerHTML. */
  escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  },

  /** Format an ISO timestamp as a short, readable local date + time. */
  formatDate(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    return date.toLocaleString();
  },

  /**
   * Pull a human-friendly message out of an error response. FastAPI sends
   * validation errors (422) as a list under "detail"; everything else is a
   * plain string under "detail".
   */
  async errorMessage(response, fallback = "Something went wrong.") {
    const data = await response.json().catch(() => ({}));
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg).join(" ");
    }
    return data.detail || fallback;
  },

  /** Show a message in a `.banner` element (type = "error" | "success"). */
  showBanner(el, message, type = "error") {
    if (!el) return;
    el.textContent = message;
    el.className = `banner show ${type}`;
  },

  /** Hide a `.banner` element. */
  hideBanner(el) {
    if (!el) return;
    el.textContent = "";
    el.className = "banner";
  },
};
