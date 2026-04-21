/* ─── config.js — Environment configuration ─────────────────────
 *
 * Edit this file to switch environments.
 * In production, replace API_BASE with your deployed backend URL.
 * This file is loaded first so all other modules can use window.Config.
 * ────────────────────────────────────────────────────────────────── */
window.Config = {
  // Backend base URL — no trailing slash
  API_BASE: 'https://linkvault-api.onrender.com',

  // Short-URL base (usually same as API_BASE in Phase 1;
  // may differ in production if you serve the redirect on a CDN/subdomain)
  SHORT_URL_BASE: 'https://linkvault-api.onrender.com',

  // App display name
  APP_NAME: 'LinkVault',

  // Default pagination size
  DEFAULT_PAGE_SIZE: 20,

  // Feature flags — disable UI sections globally when not yet deployed
  FEATURES: {
    ADMIN_PANEL: true,          // Show/hide the Platform Admin nav link
    LINK_ANALYTICS: true,       // Show per-link analytics button
    PROJECT_ANALYTICS: true,    // Show per-project analytics button
  },
};

/* ── Usage from other modules ────────────────────────────────────
 *   Config.API_BASE          → 'http://localhost:8000'
 *   Config.FEATURES.ADMIN_PANEL → true
 * ─────────────────────────────────────────────────────────────── */
