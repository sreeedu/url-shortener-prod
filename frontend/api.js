/* ─── api.js — HTTP client with auth & token refresh ────────── */
// API_BASE resolved from config.js (window.Config); falls back to localhost for dev
const API_BASE = (window.Config && window.Config.API_BASE) || 'http://localhost:8000';

const Store = {
  getAccess()  { return localStorage.getItem('access_token'); },
  getRefresh() { return localStorage.getItem('refresh_token'); },
  setTokens(a, r) {
    localStorage.setItem('access_token', a);
    if (r) localStorage.setItem('refresh_token', r);
  },
  clear() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  },
  getUser()  { try { return JSON.parse(localStorage.getItem('user')); } catch { return null; } },
  setUser(u) { localStorage.setItem('user', JSON.stringify(u)); },
};

let _refreshingPromise = null;
async function _refresh() {
  if (_refreshingPromise) return _refreshingPromise;
  _refreshingPromise = (async () => {
    const rt = Store.getRefresh();
    if (!rt) throw new Error('No refresh token');
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    });
    if (!res.ok) throw new Error('Refresh failed');
    const data = await res.json();
    Store.setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  })();
  try { return await _refreshingPromise; }
  finally { _refreshingPromise = null; }
}

async function apiFetch(path, { method = 'GET', body, auth = true, raw = false } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = Store.getAccess();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);

  let res = await fetch(`${API_BASE}${path}`, opts);

  if (res.status === 401 && auth) {
    try {
      const newToken = await _refresh();
      headers['Authorization'] = `Bearer ${newToken}`;
      res = await fetch(`${API_BASE}${path}`, { ...opts, headers });
    } catch {
      Store.clear();
      window.location.hash = '#/login';
      throw new Error('Session expired');
    }
  }

  if (raw) return res;
  if (res.status === 204) return null;

  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = json.detail || `HTTP ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return json;
}

// ── Auth ──────────────────────────────────────────────────────
const AuthAPI = {
  signup:  (email, password) => apiFetch('/api/auth/signup',  { method:'POST', body:{email,password}, auth:false }),
  login:   (email, password) => apiFetch('/api/auth/login',   { method:'POST', body:{email,password}, auth:false }),
  me:      ()               => apiFetch('/api/auth/me'),
  forgot:  (email)          => apiFetch('/api/auth/forgot-password', { method:'POST', body:{email}, auth:false }),
  reset:   (token, password) => apiFetch('/api/auth/reset-password', { method:'POST', body:{token, new_password:password, confirm_password:password}, auth:false }),
  refresh: (refresh_token)  => apiFetch('/api/auth/refresh',  { method:'POST', body:{refresh_token}, auth:false }),
  verify:  (token)          => apiFetch('/api/auth/verify', { method:'POST', body:{token}, auth:false }),
  resendVerification: (email) => apiFetch('/api/auth/resend-verification', { method:'POST', body:{email}, auth:false }),
};

// ── Projects ──────────────────────────────────────────────────
const ProjectsAPI = {
  list:       (page=1, per_page=20) => apiFetch(`/api/projects?page=${page}&per_page=${per_page}`),
  get:        (id)               => apiFetch(`/api/projects/${id}`),
  create:     (body)             => apiFetch('/api/projects', { method:'POST', body }),
  update:     (id, body)         => apiFetch(`/api/projects/${id}`, { method:'PATCH', body }),
  delete:     (id)               => apiFetch(`/api/projects/${id}`, { method:'DELETE', raw:true }),
  analytics:  (id)               => apiFetch(`/api/projects/${id}/analytics`),
};

// ── Links ─────────────────────────────────────────────────────
const LinksAPI = {
  list:      (pid, page=1, per_page=20) => apiFetch(`/api/projects/${pid}/links?page=${page}&per_page=${per_page}`),
  get:       (pid, id)               => apiFetch(`/api/projects/${pid}/links/${id}`),
  create:    (pid, body)             => apiFetch(`/api/projects/${pid}/links`, { method:'POST', body }),
  update:    (pid, id, body)         => apiFetch(`/api/projects/${pid}/links/${id}`, { method:'PATCH', body }),
  delete:    (pid, id)               => apiFetch(`/api/projects/${pid}/links/${id}`, { method:'DELETE', raw:true }),
  analytics: (pid, id)               => apiFetch(`/api/projects/${pid}/links/${id}/analytics`),
};

// ── Platform ──────────────────────────────────────────────────
const PlatformAPI = {
  stats:       ()              => apiFetch('/api/platform/stats'),
  users:       (params={})     => apiFetch(`/api/platform/users?${new URLSearchParams(params)}`),
  getUser:     (id)            => apiFetch(`/api/platform/users/${id}`),
  deactivate:  (id)            => apiFetch(`/api/platform/users/${id}/deactivate`, { method:'PATCH' }),
  reactivate:  (id)            => apiFetch(`/api/platform/users/${id}/reactivate`, { method:'PATCH' }),
  projects:    (params={})     => apiFetch(`/api/platform/projects?${new URLSearchParams(params)}`),
  links:       (params={})     => apiFetch(`/api/platform/links?${new URLSearchParams(params)}`),
  auditLogs:   (params={})     => apiFetch(`/api/platform/audit-logs?${new URLSearchParams(params)}`),
  inviteAdmin: (email)         => apiFetch('/api/platform/admins/invite', { method:'POST', body:{ email } }),
  acceptAdmin: (token)         => apiFetch('/api/platform/admins/accept', { method:'POST', body:{ token } }),
};

// ── AI ────────────────────────────────────────────────────────
const AIAPI = {
  insights: (linkId, prompt = null) => apiFetch(`/api/ai/insights/link/${linkId}`, { method: 'POST', body: { user_prompt: prompt } }),
  proposeCampaign: (prompt) => apiFetch('/api/ai/propose-campaign', { method: 'POST', body: { prompt } }),
  checkShortCode: (code) => apiFetch(`/api/ai/check-short-code?code=${encodeURIComponent(code)}`),
};

// ── Compare ───────────────────────────────────────────────────
const CompareAPI = {
  insight: (linkIds) => apiFetch('/api/ai/compare', { method: 'POST', body: { link_ids: linkIds } }),
};
