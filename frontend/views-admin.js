/* ─── views-admin.js — Platform Admin Panel ──────────────────── */

async function renderAdmin() {
  const view = document.getElementById('main-view');
  view.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">Admin Panel</h1>
        <p class="page-subtitle">Platform management &amp; oversight</p>
      </div>
      <button class="btn btn--ghost" id="admin-refresh-btn">
        <svg class="icon"><use href="#ico-refresh"/></svg> Refresh
      </button>
    </div>
    <div class="tabs" id="admin-tabs">
      <button class="tab-btn active" data-tab="stats" onclick="switchAdminTab('stats',this)">Stats</button>
      <button class="tab-btn" data-tab="users" onclick="switchAdminTab('users',this)">Users</button>
      <button class="tab-btn" data-tab="projects" onclick="switchAdminTab('projects',this)">Projects</button>
      <button class="tab-btn" data-tab="links" onclick="switchAdminTab('links',this)">Links</button>
      <button class="tab-btn" data-tab="logs" onclick="switchAdminTab('logs',this)">Audit Logs</button>
    </div>
    <div id="admin-tab-content"></div>`;

  document.getElementById('admin-refresh-btn').onclick = () => {
    const active = document.querySelector('#admin-tabs .tab-btn.active');
    if (active) switchAdminTab(active.dataset.tab, active);
  };
  switchAdminTab('stats', document.querySelector('#admin-tabs .tab-btn'));
}

function switchAdminTab(tab, btn) {
  document.querySelectorAll('#admin-tabs .tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const content = document.getElementById('admin-tab-content');
  switch(tab) {
    case 'stats':    loadAdminStats(content);   break;
    case 'users':    loadAdminUsers(content);   break;
    case 'projects': loadAdminProjects(content);break;
    case 'links':    loadAdminLinks(content);   break;
    case 'logs':     loadAuditLogs(content);    break;
  }
}

async function loadAdminStats(container) {
  container.innerHTML = `<div class="skeleton" style="height:300px"></div>`;
  try {
    const s = await PlatformAPI.stats();
    container.innerHTML = `
      <div class="card-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr));margin-bottom:24px">
        ${adminStatCard(s.total_users, 'Total Users')}
        ${adminStatCard(s.signups_today, 'Signups Today')}
        ${adminStatCard(s.signups_this_week, 'Signups (7d)')}
        ${adminStatCard(s.active_users_30d, 'Active (30d)')}
        ${adminStatCard(s.total_projects, 'Projects')}
        ${adminStatCard(s.total_links, 'Links')}
        ${adminStatCard(s.total_clicks, 'Total Clicks')}
        ${adminStatCard(s.bot_percentage + '%', 'Bot %')}
      </div>
      <div class="chart-box">
        <div class="chart-title">Clicks — Last 30 Days</div>
        ${timelineChart(s.clicks_over_time||[], 'timeline-canvas-admin')}
      </div>`;
    renderTimelineChart('timeline-canvas-admin', s.clicks_over_time || []);
  } catch(err) {
    container.innerHTML = `<p class="form-error" style="padding:24px">${err.message}</p>`;
  }
}

function adminStatCard(val, lbl) {
  return `<div class="card stat-card fade-in">
    <div class="stat-card-val">${fmtNum(val)}</div>
    <div class="stat-card-lbl">${lbl}</div>
  </div>`;
}

let _userCursor = null, _userSearch = '', _userActiveFilter = null;
async function loadAdminUsers(container, cursor = null, append = false) {
  if (!append) {
    _userCursor = null; _userSearch = ''; _userActiveFilter = null;
    container.innerHTML = `
      <div class="filter-bar">
        <div class="search-wrap">
          <svg class="icon"><use href="#ico-search"/></svg>
          <input id="admin-user-search" type="text" placeholder="Search by email…"/>
        </div>
        <select id="admin-user-status" style="width:auto">
          <option value="">All Users</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
        <button class="btn btn--ghost btn--sm" onclick="applyUserFilters()">
          <svg class="icon"><use href="#ico-search"/></svg> Filter
        </button>
        <button class="btn btn--primary btn--sm" style="margin-left:auto" onclick="adminInvitePrompt()">
          Invite Admin
        </button>
      </div>
      <div id="admin-users-table"><div class="skeleton" style="height:200px"></div></div>`;
    document.getElementById('admin-user-search').addEventListener('keydown', e => {
      if (e.key === 'Enter') applyUserFilters();
    });
  }
  const params = { per_page: 50 };
  if (_userSearch) params.search = _userSearch;
  if (_userActiveFilter !== null) params.is_active = _userActiveFilter;
  if (cursor) params.cursor = cursor;

  const tableWrap = document.getElementById('admin-users-table') || container.querySelector('#admin-users-table');
  if (!tableWrap) return;
  if (!append) tableWrap.innerHTML = `<div class="skeleton" style="height:200px"></div>`;

  try {
    const data = await PlatformAPI.users(params);
    _userCursor = data.next_cursor;
    const html = `
      <div class="table-wrapper">
        <table>
          <thead><tr>
            <th>Email</th><th>Status</th><th>Projects</th><th>Links</th>
            <th>Clicks</th><th>Last Login</th><th>Joined</th><th>Actions</th>
          </tr></thead>
          <tbody>
            ${data.users.map(u=>`<tr id="admin-user-${u.id}">
              <td>
                <div style="display:flex;align-items:center;gap:8px">
                  ${escHtml(u.email)}
                  ${u.is_platform_admin ? '<span class="badge badge--purple">Admin</span>' : ''}
                </div>
              </td>
              <td>
                <span class="badge ${u.is_active?'badge--green':'badge--red'}">${u.is_active?'Active':'Inactive'}</span>
                ${u.is_verified ? '<span class="badge badge--blue" style="margin-left:4px">Verified</span>' : ''}
              </td>
              <td>${u.project_count}</td>
              <td>${u.link_count}</td>
              <td>${fmtNum(u.total_clicks)}</td>
              <td class="text-muted text-sm">${u.last_login_at ? timeSince(u.last_login_at) : 'Never'}</td>
              <td class="text-muted text-sm">${fmtDate(u.created_at)}</td>
              <td>
                <div class="table-actions">
                  ${u.is_active
                    ? `<button class="btn btn--sm btn--ghost" onclick="adminToggleUser('${u.id}',false)" style="color:var(--danger);border-color:var(--danger)">Deactivate</button>`
                    : `<button class="btn btn--sm btn--success-outline" onclick="adminToggleUser('${u.id}',true)">Reactivate</button>`
                  }
                </div>
              </td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <span class="pagination-info">${data.total_count} users total</span>
        ${_userCursor ? `<button class="btn btn--ghost btn--sm" onclick="loadMoreUsers()">Load more</button>` : ''}
      </div>`;
    tableWrap.innerHTML = html;
  } catch(err) {
    tableWrap.innerHTML = `<p class="form-error" style="padding:24px">${err.message}</p>`;
  }
}

function applyUserFilters() {
  _userSearch = (document.getElementById('admin-user-search')?.value||'').trim();
  const sv = document.getElementById('admin-user-status')?.value;
  _userActiveFilter = sv === '' ? null : sv === 'true';
  loadAdminUsers(document.getElementById('admin-tab-content'));
}

function loadMoreUsers() {
  loadAdminUsers(document.getElementById('admin-tab-content'), _userCursor, true);
}

async function adminToggleUser(userId, activate) {
  try {
    await (activate ? PlatformAPI.reactivate(userId) : PlatformAPI.deactivate(userId));
    Toast.success(activate ? 'User reactivated.' : 'User deactivated.');
    loadAdminUsers(document.getElementById('admin-tab-content'));
  } catch(err) { Toast.error(err.message); }
}

async function loadAdminProjects(container) {
  container.innerHTML = `<div class="skeleton" style="height:200px"></div>`;
  try {
    const data = await PlatformAPI.projects({ per_page: 50 });
    container.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead><tr><th>Name</th><th>Slug</th><th>Owner</th><th>Links</th><th>Status</th><th>Created</th></tr></thead>
          <tbody>
            ${data.projects.map(p=>`<tr>
              <td><strong>${escHtml(p.name)}</strong>${p.is_default?'<span class="badge badge--purple" style="margin-left:6px">Default</span>':''}</td>
              <td class="text-mono text-sm">${escHtml(p.slug)}</td>
              <td class="text-sm text-muted">${escHtml(p.owner_email || p.owner_user_id || p.owner_org_id || '—')}</td>
              <td>${p.link_count}</td>
              <td><span class="badge ${p.is_active?'badge--green':'badge--red'}">${p.is_active?'Active':'Inactive'}</span></td>
              <td class="text-sm text-muted">${fmtDate(p.created_at)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <p class="text-sm text-muted" style="margin-top:10px">${data.total_count} total projects</p>`;
  } catch(err) {
    container.innerHTML = `<p class="form-error" style="padding:24px">${err.message}</p>`;
  }
}

async function loadAdminLinks(container) {
  container.innerHTML = `<div class="skeleton" style="height:200px"></div>`;
  try {
    const data = await PlatformAPI.links({ per_page: 50 });
    container.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead><tr><th>Short Code</th><th>Destination</th><th>Clicks</th><th>Status</th><th>Created By</th><th>Created</th></tr></thead>
          <tbody>
            ${data.links.map(l=>`<tr>
              <td><span class="short-code">${escHtml(l.short_code)}</span></td>
              <td><span class="link-url" title="${escHtml(l.original_url)}">${escHtml(l.original_url)}</span></td>
              <td><span class="badge badge--blue">${fmtNum(l.click_count)}</span></td>
              <td><span class="badge ${l.is_active?'badge--green':'badge--gray'}">${l.is_active?'Active':'Inactive'}</span></td>
              <td class="text-sm text-muted">${escHtml(l.created_by_email || l.created_by || '—')}</td>
              <td class="text-sm text-muted">${fmtDate(l.created_at)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <p class="text-sm text-muted" style="margin-top:10px">${data.total_count} total links</p>`;
  } catch(err) {
    container.innerHTML = `<p class="form-error" style="padding:24px">${err.message}</p>`;
  }
}

const AUDIT_ACTION_LABELS = {
  USER_SIGNED_UP:'Signed Up', USER_LOGGED_IN:'Logged In',
  USER_PASSWORD_RESET_REQUESTED:'Reset Requested', USER_PASSWORD_RESET_COMPLETED:'Password Reset',
  PROJECT_CREATED:'Project Created', PROJECT_UPDATED:'Project Updated',
  PROJECT_DEACTIVATED:'Project Deactivated', PROJECT_REACTIVATED:'Project Reactivated',
  PROJECT_DELETED:'Project Deleted',
  LINK_CREATED:'Link Created', LINK_UPDATED:'Link Updated',
  LINK_DEACTIVATED:'Link Deactivated', LINK_REACTIVATED:'Link Reactivated',
  LINK_DELETED:'Link Deleted',
  PLATFORM_USER_VIEWED:'User Viewed (admin)', PLATFORM_USER_DEACTIVATED:'User Deactivated (admin)',
  PLATFORM_USER_REACTIVATED:'User Reactivated (admin)',
};

let _logCursor = null;
async function loadAuditLogs(container, cursor = null, append = false) {
  if (!append) {
    _logCursor = null;
    container.innerHTML = `
      <div class="filter-bar" style="margin-bottom:16px">
        <div class="search-wrap">
          <svg class="icon"><use href="#ico-search"/></svg>
          <input id="log-action-filter" type="text" placeholder="Filter by action (e.g. LINK_CREATED)…"/>
        </div>
        <button class="btn btn--ghost btn--sm" onclick="applyLogFilters()">
          <svg class="icon"><use href="#ico-search"/></svg> Filter
        </button>
      </div>
      <div id="audit-log-table"><div class="skeleton" style="height:200px"></div></div>`;
    document.getElementById('log-action-filter').addEventListener('keydown', e => {
      if (e.key === 'Enter') applyLogFilters();
    });
  }
  const params = { per_page: 50 };
  if (cursor) params.cursor = cursor;
  const actionFilter = (document.getElementById('log-action-filter')?.value||'').trim().toUpperCase();
  if (actionFilter) params.action = actionFilter;

  const tableWrap = document.getElementById('audit-log-table');
  if (!tableWrap) return;
  if (!append) tableWrap.innerHTML = `<div class="skeleton" style="height:200px"></div>`;

  try {
    const data = await PlatformAPI.auditLogs(params);
    _logCursor = data.next_cursor;
    const badge = (a) => {
      const lbl = AUDIT_ACTION_LABELS[a] || a;
      const cls = a.includes('DELETE')||a.includes('DEACTIVATE') ? 'badge--red'
                : a.includes('CREATE')||a.includes('SIGNUP')||a.includes('REACTIVATE') ? 'badge--green'
                : 'badge--blue';
      return `<span class="badge ${cls}">${lbl}</span>`;
    };
    tableWrap.innerHTML = `
      <div class="table-wrapper">
        <table>
          <thead><tr><th>Action</th><th>Actor</th><th>Target</th><th>IP</th><th>Time</th></tr></thead>
          <tbody>
            ${data.logs.map(l=>`<tr>
              <td>${badge(l.action)}</td>
              <td class="text-sm">${escHtml(l.actor_email||'—')}</td>
              <td class="text-sm text-muted">${escHtml(l.target_type||'—')}${l.target_id?` <span style="font-family:monospace;font-size:11px">${l.target_id.slice(0,8)}…</span>`:''}</td>
              <td class="text-sm text-muted">${l.ip_address||'—'}</td>
              <td class="text-sm text-muted">${timeSince(l.created_at)}</td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      ${_logCursor ? `<div style="text-align:center;margin-top:12px"><button class="btn btn--ghost btn--sm" onclick="loadMoreLogs()">Load older</button></div>` : ''}`;
  } catch(err) {
    tableWrap.innerHTML = `<p class="form-error" style="padding:24px">${err.message}</p>`;
  }
}

function applyLogFilters() {
  loadAuditLogs(document.getElementById('admin-tab-content'));
}
function loadMoreLogs() {
  loadAuditLogs(document.getElementById('admin-tab-content'), _logCursor, true);
}

async function adminInvitePrompt() {
  const email = prompt("Enter the email address of the existing user you want to invite as a Platform Admin:");
  if (!email || !email.trim()) return;
  
  try {
    const res = await PlatformAPI.inviteAdmin(email.trim());
    Toast.success(res.message || `Invitation sent to ${email}`);
  } catch (err) {
    Toast.error(err.message);
  }
}

