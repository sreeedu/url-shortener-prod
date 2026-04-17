/* ─── app.js — Main entry: Router, Modal, Toast, Utils ──────── */
/* Loads all modules lazily via DOM scripts (no bundler needed)  */

(function bootstrap() {
  const SCRIPTS = ['api.js','auth.js','views-analytics.js','views-projects.js','views-links.js','views-admin.js','views-comparison.js'];
  let loaded = 0;
  SCRIPTS.forEach(src => {
    const s = document.createElement('script');
    s.src = src;
    s.onload = () => { if (++loaded === SCRIPTS.length) init(); };
    s.onerror = () => console.error('Failed to load', src);
    document.head.appendChild(s);
  });
})();

/* ─── Utilities ──────────────────────────────────────────────── */
function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function fmtNum(n) {
  if (n === undefined || n === null) return '0';
  n = Number(n);
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1)+'M';
  if (n >= 1_000)     return (n/1_000).toFixed(1)+'K';
  return String(n);
}
function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString(undefined, { year:'numeric', month:'short', day:'numeric' });
}
function timeSince(d) {
  if (!d) return '—';
  const sec = Math.floor((Date.now() - new Date(d).getTime()) / 1000);
  if (sec < 60)   return 'just now';
  if (sec < 3600) return Math.floor(sec/60) + 'm ago';
  if (sec < 86400) return Math.floor(sec/3600) + 'h ago';
  return Math.floor(sec/86400) + 'd ago';
}
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    const orig = btn.innerHTML;
    btn.innerHTML = `<svg class="icon" style="color:var(--success)"><use href="#ico-check"/></svg>`;
    setTimeout(() => { btn.innerHTML = orig; }, 1500);
  } catch { Toast.error('Copy failed'); }
}
function navigateTo(path) { window.location.hash = '#' + path; }

/* ─── Toast ──────────────────────────────────────────────────── */
const Toast = {
  _show(msg, type, duration = 3500) {
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    const icon = type === 'success' ? '#ico-check' : type === 'error' ? '#ico-alert' : '#ico-alert';
    el.innerHTML = `
      <svg class="icon toast-icon"><use href="${icon}"/></svg>
      <span class="toast-msg">${escHtml(msg)}</span>`;
    const container = document.getElementById('toast-container');
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, duration);
  },
  success(msg) { this._show(msg, 'success'); },
  error(msg)   { this._show(msg, 'error'); },
  info(msg)    { this._show(msg, 'info'); },
};

/* ─── Modal ──────────────────────────────────────────────────── */
const Modal = {
  show(title, html, sizeClass = '') {
    const overlay = document.getElementById('modal-overlay');
    const box = document.getElementById('modal-box');
    box.className = `modal-box ${sizeClass}`;
    document.getElementById('modal-content').innerHTML =
      `<h2 class="modal-title">${escHtml(title)}</h2>${html}`;
    overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  },
  setContent(html) {
    document.getElementById('modal-content').innerHTML = html;
  },
  hide() {
    document.getElementById('modal-overlay').classList.add('hidden');
    document.body.style.overflow = '';
  },
};

/* ─── Confirm dialog ─────────────────────────────────────────── */
const Confirm = {
  _cb: null,
  show(title, msg, onConfirm) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-msg').textContent   = msg;
    document.getElementById('confirm-overlay').classList.remove('hidden');
    this._cb = onConfirm;
  },
  hide() { document.getElementById('confirm-overlay').classList.add('hidden'); },
};

/* ─── Router ─────────────────────────────────────────────────── */
const ROUTES = {
  '/':                { auth: false, render: () => { showLanding(); if(typeof renderLanding === 'function') renderLanding(); } },
  '/landing':         { auth: false, render: () => { showLanding(); if(typeof renderLanding === 'function') renderLanding(); } },
  '/login':           { auth: false, render: () => { showAuth(); renderLogin(); } },
  '/signup':          { auth: false, render: () => { showAuth(); renderSignup(); } },
  '/forgot-password': { auth: false, render: () => { showAuth(); renderForgotPassword(); } },
  '/reset-password':  { auth: false, render: (p) => { showAuth(); renderResetPassword(p.token); } },
  '/verify':          { auth: false, render: (p) => { renderVerifyEmail(p.token); } },
  '/accept-admin':    { auth: false, render: (p) => { renderAcceptAdmin(p.token); } },
  '/dashboard':       { auth: true,  render: () => { showApp(); renderDashboard(); } },
  '/projects/:id':    { auth: true,  render: (p) => { showApp(); renderProjectDetail(p.id); } },
  '/admin':           { auth: true,  render: () => { showApp(); renderAdmin(); }, adminOnly: true },
};

function parseHash() {
  const hash = window.location.hash.replace(/^#/, '') || '/';
  for (const [pattern, route] of Object.entries(ROUTES)) {
    const keys = [];
    const regexStr = pattern.replace(/:([^/]+)/g, (_, k) => { keys.push(k); return '([^/]+)'; });
    const m = hash.match(new RegExp(`^${regexStr}(\\?.*)?$`));
    if (m) {
      const params = {};
      keys.forEach((k, i) => params[k] = m[i + 1]);
      // parse query params
      const qs = hash.includes('?') ? hash.split('?')[1] : '';
      new URLSearchParams(qs).forEach((v, k) => params[k] = v);
      return { route, params };
    }
  }
  return null;
}

async function handleRoute() {
  const result = parseHash();
  if (!result) { window.location.hash = '/'; return; }
  const { route, params } = result;
  const token  = Store.getAccess();
  const user   = Store.getUser();

  if (route.auth && !token) { window.location.hash = '#/login'; return; }
  
  // If user is authenticated and tries to access landing, login, or signup
  const isAuthRoute = window.location.hash === '' || window.location.hash === '#/' || window.location.hash === '#/landing' || window.location.hash === '#/login' || window.location.hash === '#/signup';
  if (!route.auth && token && isAuthRoute) {
    window.location.hash = '#/dashboard'; return;
  }
  
  if (route.adminOnly && !user?.is_platform_admin) {
    Toast.error('Access denied — admin only');
    window.location.hash = '#/dashboard'; return;
  }

  // Update active nav
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (params.id) {
    document.getElementById('nav-dashboard')?.classList.add('active');
  } else if (window.location.hash.startsWith('#/admin')) {
    document.getElementById('nav-admin')?.classList.add('active');
  } else {
    document.getElementById('nav-dashboard')?.classList.add('active');
  }

  try { await route.render(params); }
  catch(err) { console.error('Route render error', err); Toast.error('Page load error: ' + err.message); }
}

function showAuth() {
  document.getElementById('landing-layout')?.classList.add('hidden');
  document.getElementById('app-layout').classList.add('hidden');
  document.getElementById('auth-layout').classList.remove('hidden');
}
function showApp() {
  document.getElementById('landing-layout')?.classList.add('hidden');
  document.getElementById('auth-layout').classList.add('hidden');
  document.getElementById('app-layout').classList.remove('hidden');
  const user = Store.getUser();
  if (user) {
    document.getElementById('user-email').textContent = user.email;
    const adminNav = document.getElementById('nav-admin');
    if (adminNav) adminNav.style.display = user.is_platform_admin ? 'flex' : 'none';
  }
}
function showLanding() {
  document.getElementById('app-layout').classList.add('hidden');
  document.getElementById('auth-layout').classList.add('hidden');
  document.getElementById('landing-layout')?.classList.remove('hidden');
}

async function renderAcceptAdmin(token) {
  if (!token) {
    Toast.error('No invitation token provided.');
    window.location.hash = '#/';
    return;
  }
  
  const accessToken = Store.getAccess();
  if (!accessToken) {
    Toast.info('Please log in first to accept your admin invitation.');
    sessionStorage.setItem('redirectAfterLogin', `#/accept-admin?token=${token}`);
    window.location.hash = '#/login';
    return;
  }
  
  try {
    const res = await PlatformAPI.acceptAdmin(token);
    Toast.success(res.message || 'You are now a platform admin.');
    const u = await AuthAPI.me();
    Store.setUser(u);
    window.location.hash = '#/admin';
  } catch (err) {
    Toast.error(err.message);
    window.location.hash = '#/';
  }
}

async function renderVerifyEmail(token) {
  if (!token) {
    Toast.error('Invalid or missing verification token.');
    window.location.hash = '#/';
    return;
  }
  try {
    const res = await AuthAPI.verify(token);
    Toast.success(res.message || 'Email verified! You can now log in.');
    window.location.hash = '#/login';
  } catch (err) {
    Toast.error(err.message || 'Verification failed. Link may be expired.');
    window.location.hash = '#/';
  }
}

/* ─── Init ───────────────────────────────────────────────────── */
function init() {
  // Modal close button
  document.getElementById('modal-close').onclick = Modal.hide;
  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-overlay')) Modal.hide();
  });

  // Confirm dialog buttons
  document.getElementById('confirm-ok').onclick = () => { Confirm.hide(); Confirm._cb?.(); };
  document.getElementById('confirm-cancel').onclick = Confirm.hide;

  // Logout
  document.getElementById('logout-btn').onclick = () => {
    Confirm.show('Logout?', 'You will be returned to the login page.', () => {
      Store.clear(); window.location.hash = '#/login'; showAuth();
    });
  };

  // Route changes
  window.addEventListener('hashchange', () => {
    handleRoute();
  });

  // Keyboard: Escape closes modal
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (!document.getElementById('confirm-overlay').classList.contains('hidden')) Confirm.hide();
      else Modal.hide();
    }
  });

  // Initial route
  const token = Store.getAccess();
  if (token) {
    showApp();
    // Silently refresh user profile
    AuthAPI.me().then(u => { Store.setUser(u); showApp(); }).catch(() => {
      Store.clear(); showLanding(); window.location.hash = '#/';
    });
  } else {
    if (!window.location.hash) {
      window.location.hash = '#/';
    }
  }
  handleRoute();
}
