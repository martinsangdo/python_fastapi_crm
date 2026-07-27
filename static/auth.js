/*
   auth.js
   -------
   The tiny bit of JavaScript that powers the frontend authentication.

   Responsibilities:
   - Store the JWT access + refresh tokens in the browser.
   - Attach the access token to API requests.
   - Redirect users to /login when they are not (or no longer) logged in.
   - Provide login / logout helpers used by the pages.

   A NOTE ON "STORING JWT SECURELY":
   We use localStorage here because it is the simplest thing that works with a
   pure JS + API frontend, and it is easy for beginners to follow. Its
   trade-off is that JavaScript (including any malicious script) can read it,
   so it is vulnerable to XSS. A more hardened setup stores the token in an
   httpOnly cookie that JavaScript cannot read. See the README for details.
*/

// The keys we use inside localStorage.
const ACCESS_KEY = "crm_access_token";
const REFRESH_KEY = "crm_refresh_token";
// Where to send the user after login. We derive it from their permissions
// (the first menu item they are allowed to see) instead of hardcoding a page,
// so e.g. a Sales user is never dropped on a Dashboard they cannot use.
const LANDING_KEY = "crm_landing_route";

// Fallback when the user has no navigation items yet (e.g. a brand-new account
// with no role assigned). Kept as a single place to change.
const DEFAULT_LANDING_ROUTE = "/dashboard";

const Auth = {
  // ---- token storage -------------------------------------------------------

  saveTokens(accessToken, refreshToken) {
    localStorage.setItem(ACCESS_KEY, accessToken);
    localStorage.setItem(REFRESH_KEY, refreshToken);
  },

  getAccessToken() {
    return localStorage.getItem(ACCESS_KEY);
  },

  getRefreshToken() {
    return localStorage.getItem(REFRESH_KEY);
  },

  clearTokens() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(LANDING_KEY);
  },

  isLoggedIn() {
    return Boolean(this.getAccessToken());
  },

  // ---- landing page (derived from permissions) -----------------------------

  /**
   * Remember where to send this user after login: the route of the first menu
   * item in their permission-filtered navigation. Falls back to a default when
   * they have no accessible modules yet.
   */
  saveLandingRoute(loginData) {
    const nav = (loginData && loginData.navigation) || [];
    const route = nav.length > 0 ? nav[0].route : DEFAULT_LANDING_ROUTE;
    localStorage.setItem(LANDING_KEY, route);
    return route;
  },

  /** The page a just-logged-in user should be sent to. */
  getLandingRoute() {
    return localStorage.getItem(LANDING_KEY) || DEFAULT_LANDING_ROUTE;
  },

  // ---- API helpers ---------------------------------------------------------

  /**
   * Log in with email + password. On success the tokens are stored.
   * Throws an Error (with the server's message) on failure.
   */
  async login(email, password) {
    const response = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Login failed.");
    }

    const data = await response.json();
    this.saveTokens(data.access_token, data.refresh_token);
    // The login response includes the permission-filtered navigation menu; use
    // its first item as the landing page for this user.
    this.saveLandingRoute(data);
    return data;
  },

  /**
   * Create a new account, then log in automatically so the user lands on the
   * dashboard right away. Throws an Error (with the server's message) on failure.
   */
  async register(fullName, email, password) {
    const response = await fetch("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: fullName, email, password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      // 422 = validation errors come back as a list under "detail".
      const message = Array.isArray(data.detail)
        ? data.detail.map((d) => d.msg).join(" ")
        : data.detail;
      throw new Error(message || "Registration failed.");
    }

    // Registration succeeded — log in with the same credentials to get tokens.
    await this.login(email, password);
  },

  /**
   * Call the API with the access token attached automatically.
   * If the token is missing or rejected, we clear it and redirect to /login.
   */
  async apiFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers, {
      Authorization: `Bearer ${this.getAccessToken()}`,
    });

    const response = await fetch(url, Object.assign({}, options, { headers }));

    // 401 = the token is missing/expired/invalid -> force a fresh login.
    if (response.status === 401) {
      this.clearTokens();
      window.location.href = "/login";
      throw new Error("Your session has expired. Please log in again.");
    }

    return response;
  },

  /** Log out: tell the server (best effort) and clear local tokens. */
  async logout() {
    try {
      await this.apiFetch("/auth/logout", { method: "POST" });
    } catch (err) {
      // Even if the network call fails, we still clear tokens below.
    }
    this.clearTokens();
    window.location.href = "/login";
  },

  /**
   * Guard a protected page. Call this at the top of pages that require login.
   * If there is no token, redirect to /login immediately.
   */
  requireLogin() {
    if (!this.isLoggedIn()) {
      window.location.href = "/login";
    }
  },
};
