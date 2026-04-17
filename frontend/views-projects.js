/* ─── views-projects.js — Dashboard & Project Detail ─────────── */

const PROJECT_COLORS = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444','#06b6d4'];

// ── Dashboard ─────────────────────────────────────────────────
async function renderDashboard() {
  const view = document.getElementById('main-view');
  view.innerHTML = `
    <div class="page-header">
      <div>
        <h1 class="page-title">Dashboard</h1>
        <p class="page-subtitle">Manage your link projects</p>
      </div>
      <div class="page-actions" style="display:flex;gap:12px;">
        <button class="btn" id="ai-campaign-btn" style="background: linear-gradient(135deg, #a855f7, #ec4899); color: white; border: none; font-weight: 500;">
          ✨ AI Campaign Builder
        </button>
        <button class="btn btn--primary" id="new-project-btn">
          <svg class="icon"><use href="#ico-plus"/></svg> New Project
        </button>
      </div>
    </div>
    <div id="projects-grid" class="card-grid">
      ${skeletonCards(6)}
    </div>`;

  document.getElementById('new-project-btn').onclick = () => showProjectModal();
  document.getElementById('ai-campaign-btn').onclick = () => showAICampaignModal();

  try {
    const data = await ProjectsAPI.list(1, 50);
    renderProjectCards(data.projects || []);
  } catch(err) {
    document.getElementById('projects-grid').innerHTML =
      `<div class="empty-state"><svg class="icon"><use href="#ico-alert"/></svg><h3>Failed to load projects</h3><p>${err.message}</p></div>`;
  }
}

function skeletonCards(n) {
  return Array.from({length:n}, () =>
    `<div class="card" style="height:160px">
       <div class="skeleton" style="height:16px;width:60%;margin-bottom:8px"></div>
       <div class="skeleton" style="height:12px;width:40%"></div>
     </div>`).join('');
}

function renderProjectCards(projects) {
  const grid = document.getElementById('projects-grid');
  if (!projects.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <svg class="icon"><use href="#ico-folder"/></svg>
        <h3>No projects yet</h3>
        <p>Create your first project to start shortening links.</p>
        <button class="btn btn--primary" onclick="showProjectModal()">
          <svg class="icon"><use href="#ico-plus"/></svg> New Project
        </button>
      </div>`;
    return;
  }
  grid.innerHTML = projects.map(p => `
    <div class="card project-card fade-in" style="--card-color:${p.color||'#6366f1'}"
         data-id="${p.id}" onclick="navigateTo('/projects/${p.id}')">
      <div class="project-card-header">
        <div>
          <div class="project-card-name">${escHtml(p.name)}</div>
          <div class="project-card-slug text-mono">${escHtml(p.slug)}</div>
        </div>
        <div class="card-actions" onclick="event.stopPropagation()">
          ${p.is_default ? '' : `
          <button class="btn btn--ghost btn--icon" title="Edit" onclick="showProjectModal('${p.id}')">
            <svg class="icon"><use href="#ico-edit"/></svg>
          </button>`}
          <button class="btn btn--ghost btn--icon" title="Analytics" onclick="showProjectAnalytics('${p.id}')">
            <svg class="icon"><use href="#ico-bar-chart"/></svg>
          </button>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
        ${p.is_default ? '<span class="badge badge--purple">Default</span>' : ''}
        <span class="badge ${p.is_active ? 'badge--green' : 'badge--red'}">${p.is_active ? 'Active' : 'Inactive'}</span>
      </div>
      ${p.description ? `<p style="font-size:12.5px;color:var(--text-muted);margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(p.description)}</p>` : ''}
      <div class="project-card-meta">
        <div class="meta-stat">
          <span class="meta-stat-val">${p.link_count ?? 0}</span>
          <span class="meta-stat-lbl">Links</span>
        </div>
        <div class="meta-stat">
          <span class="meta-stat-val">${fmtNum(p.total_clicks ?? 0)}</span>
          <span class="meta-stat-lbl">Clicks</span>
        </div>
        <div class="meta-stat">
          <span class="meta-stat-val">${fmtNum(p.clicks_this_month ?? 0)}</span>
          <span class="meta-stat-lbl">This month</span>
        </div>
      </div>
    </div>`).join('');
}

// ── Project Modal (Create / Edit) ─────────────────────────────
async function showProjectModal(projectId = null) {
  let project = null;
  if (projectId) {
    try { project = await ProjectsAPI.get(projectId); } catch {}
  }
  const title = project ? 'Edit Project' : 'New Project';
  const selColor = project?.color || PROJECT_COLORS[0];
  Modal.show(title, `
    <form id="proj-form">
      <div class="form-group">
        <label>Project Name</label>
        <input id="pf-name" type="text" maxlength="100" placeholder="My Project" value="${escHtml(project?.name||'')}" required/>
      </div>
      <div class="form-group">
        <label>Description <span style="font-weight:400;text-transform:none;color:var(--text-muted)">(optional)</span></label>
        <textarea id="pf-desc" maxlength="500" placeholder="What's this project for?">${escHtml(project?.description||'')}</textarea>
      </div>
      <div class="form-group">
        <label>Color</label>
        <div class="color-row" id="color-row">
          ${PROJECT_COLORS.map(c => `
            <div class="color-swatch ${c===selColor?'selected':''}" style="background:${c}"
                 data-color="${c}" title="${c}" onclick="selectColor(this)"></div>`).join('')}
        </div>
        <input type="hidden" id="pf-color" value="${selColor}"/>
      </div>
      <div id="pf-err" class="form-error mb-16" style="display:none"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px">
        <button type="button" class="btn btn--ghost" onclick="Modal.hide()">Cancel</button>
        <button type="submit" class="btn btn--primary" id="pf-submit">${project ? 'Save Changes' : 'Create Project'}</button>
      </div>
    </form>`);

  document.getElementById('proj-form').addEventListener('submit', async e => {
    e.preventDefault();
    const btn = document.getElementById('pf-submit');
    const errEl = document.getElementById('pf-err');
    errEl.style.display = 'none';
    btn.disabled = true; btn.textContent = 'Saving…';
    const body = {
      name: document.getElementById('pf-name').value.trim(),
      description: document.getElementById('pf-desc').value.trim() || null,
      color: document.getElementById('pf-color').value,
    };
    try {
      if (project) await ProjectsAPI.update(project.id, body);
      else await ProjectsAPI.create(body);
      Modal.hide();
      Toast.success(project ? 'Project updated.' : 'Project created!');
      renderDashboard();
    } catch(err) {
      errEl.textContent = err.message; errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = project ? 'Save Changes' : 'Create Project';
    }
  });
}

function selectColor(el) {
  document.querySelectorAll('#color-row .color-swatch').forEach(s => s.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('pf-color').value = el.dataset.color;
}

// ── Project Detail ─────────────────────────────────────────────
async function renderProjectDetail(projectId) {
  const view = document.getElementById('main-view');
  view.innerHTML = `<div class="breadcrumb">
    <a href="#/dashboard">Dashboard</a>
    <svg class="icon"><use href="#ico-chevron-right"/></svg>
    <span id="proj-breadcrumb">Loading…</span>
  </div>
  <div class="page-header">
    <div>
      <h1 class="page-title" id="proj-title">…</h1>
      <p class="page-subtitle" id="proj-meta"></p>
    </div>
    <div class="page-actions">
      <button class="btn btn--ghost" id="proj-analytics-btn">
        <svg class="icon"><use href="#ico-bar-chart"/></svg> Analytics
      </button>
      <button class="btn btn--ghost" id="proj-edit-btn">
        <svg class="icon"><use href="#ico-edit"/></svg> Edit
      </button>
    </div>
  </div>
  <div id="links-section"></div>`;

  // Load project
  let project;
  try {
    project = await ProjectsAPI.get(projectId);
  } catch(err) {
    view.innerHTML = `<div class="empty-state">
      <svg class="icon"><use href="#ico-alert"/></svg>
      <h3>Project not found</h3><p>${err.message}</p>
      <a href="#/dashboard" class="btn btn--ghost">← Back</a></div>`;
    return;
  }

  document.getElementById('proj-breadcrumb').textContent = project.name;
  document.getElementById('proj-title').textContent = project.name;
  document.getElementById('proj-meta').innerHTML =
    `<span class="text-mono" style="color:var(--text-muted)">${project.slug}</span>
     &nbsp;·&nbsp; ${project.link_count} links &nbsp;·&nbsp; ${fmtNum(project.total_clicks)} total clicks`;
  document.getElementById('proj-analytics-btn').onclick = () => showProjectAnalytics(projectId);
  document.getElementById('proj-edit-btn').onclick = () => showProjectModal(projectId);

  renderLinksSection(project);
}

// ─── Project Analytics ────────────────────────────────────────

/**
 * Build the full analytics modal HTML from a ProjectAnalyticsResponse object.
 * Kept as a pure function (no DOM side-effects) so it can be tested in isolation
 * and so renderTimelineChart() can be called after the HTML is in the DOM.
 */
function _buildProjectAnalyticsHTML(a) {
  // ── Bot warning banner (only when bots were detected) ──────────
  const botBanner = a.bot_clicks > 0
    ? `<div class="mb-16" style="padding:10px 14px;border-radius:8px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);font-size:12.5px;color:#fbbf24">
        ⚠ ${fmtNum(a.bot_clicks)} bot click${a.bot_clicks > 1 ? 's' : ''} detected and excluded from human totals.
      </div>`
    : '';

  // ── Top links ranked table ──────────────────────────────────────
  const RANK_COLORS = ['#f59e0b', '#94a3b8', '#cd7c2e'];  // gold, silver, bronze
  const topLinksSection = (a.top_links && a.top_links.length)
    ? `<div class="chart-box mb-16">
        <div class="chart-title">Top Links by Clicks</div>
        <div class="table-wrapper" style="border:none">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Short Code</th>
                <th>Title</th>
                <th style="text-align:right">Clicks</th>
              </tr>
            </thead>
            <tbody>
              ${a.top_links.map((link, i) => `
                <tr>
                  <td style="width:36px">
                    <span style="font-size:13px;font-weight:700;color:${RANK_COLORS[i] || 'var(--text-muted)'}">
                      ${i + 1}
                    </span>
                  </td>
                  <td>
                    <span class="short-code">/${escHtml(link.short_code)}</span>
                  </td>
                  <td style="color:var(--text-muted);font-size:12.5px">
                    ${link.title ? escHtml(link.title) : '—'}
                  </td>
                  <td style="text-align:right">
                    <span class="badge badge--blue">${fmtNum(link.clicks)}</span>
                  </td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`
    : '';

  // ── Peak hour label ─────────────────────────────────────────────
  const peakHourLine = (a.peak_hour !== null && a.peak_hour !== undefined)
    ? `<p class="text-sm text-muted" style="margin-top:12px;text-align:center">
        Peak hour: <strong style="color:var(--text-primary)">${formatHour(a.peak_hour)}</strong>
      </p>`
    : '';

  return `
    <h2 class="modal-title">
      ${escHtml(a.project_name)}
      <span style="font-size:13px;font-weight:500;color:var(--text-muted);margin-left:8px">— Analytics</span>
    </h2>

    <!-- Primary metrics: traffic + engagement -->
    <div class="stats-strip" style="margin-bottom:12px">
      ${statBox(a.total_clicks,      'Total Clicks')}
      ${statBox(a.human_clicks,      'Human Clicks')}
      ${statBox(a.unique_visitors,   'Unique IPs')}
      ${statBox(a.clicks_today,      'Today')}
      ${statBox(a.clicks_this_week,  'This Week')}
      ${statBox(a.clicks_this_month, 'This Month')}
    </div>

    <!-- Secondary metrics: project health -->
    <div class="stats-strip" style="grid-template-columns:repeat(3,1fr);margin-bottom:20px">
      ${statBox(a.total_links,  'Total Links')}
      ${statBox(a.active_links, 'Active Links')}
      ${statBox(a.bot_clicks,   'Bot Clicks')}
    </div>

    ${botBanner}
    ${topLinksSection}

    <!-- Audience breakdowns -->
    <div class="chart-section">
      <div class="chart-box">
        <div class="chart-title">Devices</div>
        ${donutChart(a.devices)}
      </div>
      <div class="chart-box">
        <div class="chart-title">Browsers</div>
        ${donutChart(a.browsers)}
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-box">
        <div class="chart-title">Operating Systems</div>
        ${barChart(a.os_breakdown)}
      </div>
      <div class="chart-box">
        <div class="chart-title">Top Referrers</div>
        ${barChart(a.referers, true)}
      </div>
    </div>

    <!-- 30-day timeline -->
    <div class="chart-box">
      <div class="chart-title">Clicks — Last 30 Days</div>
      ${timelineChart(a.clicks_over_time || [], 'timeline-canvas-proj')}
    </div>

    ${peakHourLine}
  `;
}

async function showProjectAnalytics(projectId) {
  Modal.show('', `<div style="height:220px" class="skeleton"></div>`, 'modal-box--lg');
  try {
    const a = await ProjectsAPI.analytics(projectId);
    Modal.setContent(_buildProjectAnalyticsHTML(a));
    renderTimelineChart('timeline-canvas-proj', a.clicks_over_time || []);
  } catch (err) {
    Modal.setContent(
      `<p class="form-error" style="text-align:center;padding:24px">${escHtml(err.message)}</p>`
    );
  }
}

// ── AI Campaign Builder ────────────────────────────────────────

let aiCampaignState = {
  step: 1,
  prompt: '',
  proposal: null
};

function showAICampaignModal() {
  aiCampaignState = { step: 1, prompt: '', proposal: null };
  _renderAICampaignModal();
}

function _renderAICampaignModal() {
  if (aiCampaignState.step === 1) {
    Modal.show('✨ AI Campaign Builder', `
      <form id="ai-campaign-form">
        <p class="mb-16 text-sm text-muted">Describe the marketing campaign you're building. Paste any links you want shortened.</p>
        <div class="form-group">
          <textarea id="ai-prompt" rows="5" placeholder="e.g. I'm running a Summer Sale in July. Create a project and add these two links: https://example.com/shoes and https://example.com/hats" required></textarea>
        </div>
        <div id="ai-err" class="form-error mb-16" style="display:none"></div>
        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px;">
          <button type="button" class="btn btn--ghost" onclick="Modal.hide()">Cancel</button>
          <button type="submit" class="btn btn--primary" id="ai-submit-btn">Generate Draft</button>
        </div>
      </form>
    `);
    
    document.getElementById('ai-campaign-form').addEventListener('submit', handleAICampaignSubmit);
    
  } else if (aiCampaignState.step === 2) {
    Modal.show('✨ AI Generating...', `
      <div style="height: 200px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 16px;">
        <div class="skeleton" style="height: 16px; width: 60%; margin-bottom: 8px;"></div>
        <div class="skeleton" style="height: 16px; width: 40%; margin-bottom: 8px;"></div>
        <div class="skeleton" style="height: 16px; width: 80%;"></div>
      </div>
    `);
  } else if (aiCampaignState.step === 3) {
    if (!aiCampaignState.proposal || !aiCampaignState.proposal.projects) return;
    
    Modal.show('Review Proposed Campaign', `
      <form id="ai-confirm-form">
        <div id="ai-projects-container" style="display:flex; flex-direction:column; gap: 32px;">
          ${aiCampaignState.proposal.projects.map((p, pIndex) => `
            <div class="card p-16 ai-project-block" data-project-index="${pIndex}" style="border: 1px solid var(--border-color); border-radius: 8px;">
              <h4 class="mb-16">Project Details</h4>
              <div class="form-group">
                <label>Project Name</label>
                <input class="ai-proj-name" type="text" value="${escHtml(p.name)}" required />
              </div>
              <div class="form-group" style="display:flex; gap:10px">
                <div style="flex:1">
                  <label>Description</label>
                  <input class="ai-proj-desc" type="text" value="${escHtml(p.description)}" />
                </div>
                <div style="width: 80px;">
                  <label>Color</label>
                  <input class="ai-proj-color" type="color" value="${p.color || '#6366f1'}" style="width:100%; height: 38px; padding:2px; border:1px solid var(--border-color); border-radius:4px" />
                </div>
              </div>
              
              <h4 class="mb-16 mt-24">Links to Shorten</h4>
              <div class="ai-links-container" style="display:flex; flex-direction:column; gap: 12px;">
                ${p.links.map((link) => `
                  <div class="card p-10 ai-link-row" style="background:var(--bg-inset); padding: 12px; border: 1px solid var(--border-color); border-radius: 6px;">
                    <div class="form-group" style="margin-bottom:8px;">
                      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                         <label style="margin:0">Original URL</label>
                         <button type="button" class="btn btn--ghost btn--sm" style="padding: 2px 6px; font-size:11px;" onclick="this.parentElement.parentElement.nextElementSibling.style.display = this.parentElement.parentElement.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">[+] UTM Tags</button>
                      </div>
                      <input class="ai-link-url" type="url" value="${escHtml(link.original_url)}" required oninput="syncUtmInputsFromUrl(this)" />
                    </div>
                    <div class="ai-utm-drawer" style="display:${link.utm_source||link.utm_medium||link.utm_campaign ? 'flex' : 'none'}; gap:6px; margin-bottom:8px; padding: 8px; background: rgba(0,0,0,0.02); border-radius:4px; border: 1px dashed var(--border-color);">
                       <input class="ai-utm-source text-sm" placeholder="utm_source" value="${escHtml(link.utm_source || '')}" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
                       <input class="ai-utm-medium text-sm" placeholder="utm_medium" value="${escHtml(link.utm_medium || '')}" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
                       <input class="ai-utm-campaign text-sm" placeholder="utm_campaign" value="${escHtml(link.utm_campaign || '')}" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
                    </div>
                    <div style="display:flex; gap:10px;">
                      <div class="form-group" style="flex:1; margin-bottom:0;">
                        <label>Title</label>
                        <input class="ai-link-title" type="text" value="${escHtml(link.title)}" required />
                      </div>
                      <div class="form-group" style="flex:1; margin-bottom:0; position:relative;">
                        <label>Short Code (Optional)</label>
                        <input class="ai-link-code" type="text" value="${escHtml(link.custom_code || '')}" oninput="checkAICode(this)" />
                        <div class="code-err text-xs" style="color:var(--text-danger); display:none; position:absolute; bottom:-16px; left:0;"></div>
                      </div>
                      <button type="button" class="btn btn--ghost btn--icon" style="align-self:flex-end;" onclick="this.closest('.ai-link-row').remove(); checkAllAICodes();" title="Remove Link">
                         <svg class="icon" style="color:var(--text-danger)"><use href="#ico-trash"/></svg>
                      </button>
                    </div>
                  </div>
                `).join('')}
              </div>
              <button type="button" class="btn btn--ghost mt-16" onclick="addAILinkRow(this)" style="align-self: flex-start">+ Add Link</button>
            </div>
          `).join('')}
        </div>
        <button type="button" class="btn btn--ghost mt-24" style="width:100%; border:1px dashed var(--border-color);" onclick="addAIProjectBlock()">+ Add New Project</button>
        <div id="ai-err-confirm" class="form-error mb-16 mt-16" style="display:none"></div>
        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px;">
          <button type="button" class="btn btn--ghost" onclick="aiCampaignState.step = 1; _renderAICampaignModal()">Back</button>
          <button type="submit" class="btn btn--primary" id="ai-confirm-btn">Confirm & Create</button>
        </div>
      </form>
    `, 'modal-box--lg'); 
    
    document.getElementById('ai-confirm-form').addEventListener('submit', handleConfirmCampaign);
    setTimeout(() => { document.querySelectorAll('.ai-link-code').forEach(input => checkAICode(input)); }, 100);
  } else if (aiCampaignState.step === 4) {
    Modal.show('AI Response', `
      <div style="text-align:center; padding: 20px;">
         <p style="font-size: 16px; margin-bottom: 24px;">${escHtml(aiCampaignState.proposal?.ai_message || "I'm sorry, I couldn't understand your request.")}</p>
         <button class="btn btn--primary" onclick="aiCampaignState.step = 1; _renderAICampaignModal()">Back to Setup</button>
      </div>    
    `);
  }
}

let aiCodeCheckTimers = new Map();
async function checkAICode(input) {
  const code = input.value.trim();
  
  if (!code) {
     input.dataset.backendStatus = 'empty';
     checkAllAICodes();
     return;
  }

  input.dataset.backendStatus = 'checking';
  checkAllAICodes(); // Disable confirm while checking

  if (aiCodeCheckTimers.has(input)) clearTimeout(aiCodeCheckTimers.get(input));
  
  aiCodeCheckTimers.set(input, setTimeout(async () => {
     try {
        const res = await AIAPI.checkShortCode(code);
        input.dataset.backendStatus = res.exists ? 'in_use' : 'available';
        checkAllAICodes();
     } catch(e) {
        input.dataset.backendStatus = 'error';
        checkAllAICodes();
     }
  }, 350));
}

function checkAllAICodes() {
  const inputs = Array.from(document.querySelectorAll('.ai-link-code'));
  const codeCounts = {};
  
  inputs.forEach(inp => {
    const code = inp.value.trim();
    if (code) {
      codeCounts[code] = (codeCounts[code] || 0) + 1;
    }
  });

  let hasErrors = false;
  inputs.forEach(inp => {
    const code = inp.value.trim();
    const errDiv = inp.parentElement.querySelector('.code-err');
    
    if (!code) {
       errDiv.style.display = 'none';
       inp.style.borderColor = 'var(--border-color)';
       return;
    }

    if (codeCounts[code] > 1) {
      errDiv.textContent = 'Repeated code in this proposal';
      errDiv.style.display = 'block';
      inp.style.borderColor = 'var(--text-danger)';
      hasErrors = true;
    } else if (inp.dataset.backendStatus === 'in_use') {
      errDiv.textContent = 'Code already taken';
      errDiv.style.display = 'block';
      inp.style.borderColor = 'var(--text-danger)';
      hasErrors = true;
    } else if (inp.dataset.backendStatus === 'checking') {
      errDiv.style.display = 'none';
      inp.style.borderColor = 'var(--text-muted)';
      hasErrors = true; // disable confirm while fetching
    } else {
      errDiv.style.display = 'none';
      inp.style.borderColor = 'var(--text-success, #10b981)';
    }
  });

  const confirmBtn = document.getElementById('ai-confirm-btn');
  if (confirmBtn) confirmBtn.disabled = hasErrors;
}

window.addAILinkRow = function(btn) {
  const container = btn.previousElementSibling;
  container.insertAdjacentHTML('beforeend', `
    <div class="card p-10 ai-link-row" style="background:var(--bg-inset); padding: 12px; border: 1px solid var(--border-color); border-radius: 6px;">
      <div class="form-group" style="margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
           <label style="margin:0">Original URL</label>
           <button type="button" class="btn btn--ghost btn--sm" style="padding: 2px 6px; font-size:11px;" onclick="this.parentElement.parentElement.nextElementSibling.style.display = this.parentElement.parentElement.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">[+] UTM Tags</button>
        </div>
        <input class="ai-link-url" type="url" value="" required oninput="syncUtmInputsFromUrl(this)" />
      </div>
      <div class="ai-utm-drawer" style="display:none; gap:6px; margin-bottom:8px; padding: 8px; background: rgba(0,0,0,0.02); border-radius:4px; border: 1px dashed var(--border-color);">
         <input class="ai-utm-source text-sm" placeholder="utm_source" value="" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
         <input class="ai-utm-medium text-sm" placeholder="utm_medium" value="" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
         <input class="ai-utm-campaign text-sm" placeholder="utm_campaign" value="" oninput="updateRowUrL(this)" style="flex:1; padding:4px 8px; height:28px;" />
      </div>
      <div style="display:flex; gap:10px;">
        <div class="form-group" style="flex:1; margin-bottom:0;">
          <label>Title</label>
          <input class="ai-link-title" type="text" value="" required />
        </div>
        <div class="form-group" style="flex:1; margin-bottom:0; position:relative;">
          <label>Short Code (Optional)</label>
          <input class="ai-link-code" type="text" value="" oninput="checkAICode(this)" />
          <div class="code-err text-xs" style="color:var(--text-danger); display:none; position:absolute; bottom:-16px; left:0;"></div>
        </div>
        <button type="button" class="btn btn--ghost btn--icon" style="align-self:flex-end;" onclick="this.closest('.ai-link-row').remove(); checkAllAICodes();" title="Remove Link">
           <svg class="icon" style="color:var(--text-danger)"><use href="#ico-trash"/></svg>
        </button>
      </div>
    </div>
  `);
};

window.addAIProjectBlock = function() {
  const container = document.getElementById('ai-projects-container');
  const pIndex = container.children.length;
  container.insertAdjacentHTML('beforeend', `
    <div class="card p-16 ai-project-block" data-project-index="${pIndex}" style="border: 1px solid var(--border-color); border-radius: 8px;">
      <h4 class="mb-16">Project Details</h4>
      <div class="form-group">
        <label>Project Name</label>
        <input class="ai-proj-name" type="text" value="" required />
      </div>
      <div class="form-group" style="display:flex; gap:10px">
        <div style="flex:1">
          <label>Description</label>
          <input class="ai-proj-desc" type="text" value="" />
        </div>
        <div style="width: 80px;">
          <label>Color</label>
          <input class="ai-proj-color" type="color" value="#6366f1" style="width:100%; height: 38px; padding:2px; border:1px solid var(--border-color); border-radius:4px" />
        </div>
      </div>
      
      <h4 class="mb-16 mt-24">Links to Shorten</h4>
      <div class="ai-links-container" style="display:flex; flex-direction:column; gap: 12px;">
      </div>
      <button type="button" class="btn btn--ghost mt-16" onclick="addAILinkRow(this)" style="align-self: flex-start">+ Add Link</button>
    </div>
  `);
};

async function handleAICampaignSubmit(e) {
  e.preventDefault();
  const prompt = document.getElementById('ai-prompt').value.trim();
  if (!prompt) return;
  
  aiCampaignState.prompt = prompt;
  aiCampaignState.step = 2;
  _renderAICampaignModal();
  
  try {
    const res = await AIAPI.proposeCampaign(prompt);
    aiCampaignState.proposal = res;
    if (res.projects && res.projects.length > 0) {
      aiCampaignState.step = 3; 
    } else if (res.ai_message) {
      aiCampaignState.step = 4;
    } else {
      throw new Error("No projects could be parsed from your prompt.");
    }
    _renderAICampaignModal();
  } catch(err) {
    aiCampaignState.step = 1;
    _renderAICampaignModal();
    setTimeout(() => {
       document.getElementById('ai-prompt').value = prompt;
       const errEl = document.getElementById('ai-err');
       errEl.textContent = err.message || "Failed to generate campaign.";
       errEl.style.display = 'block';
    }, 10);
  }
}

async function handleConfirmCampaign(e) {
  e.preventDefault();
  const btn = document.getElementById('ai-confirm-btn');
  const errEl = document.getElementById('ai-err-confirm');
  errEl.style.display = 'none';
  btn.disabled = true; 
  btn.textContent = 'Creating...';
  
  try {
    const projectBlocks = document.querySelectorAll('.ai-project-block');
    let failedCount = 0;
    let projSuccessCount = 0;

    for (const block of projectBlocks) {
      const name = block.querySelector('.ai-proj-name').value.trim();
      const desc = block.querySelector('.ai-proj-desc').value.trim() || null;
      const color = block.querySelector('.ai-proj-color').value;
      
      const linkRows = block.querySelectorAll('.ai-link-row');
      const linksToCreate = Array.from(linkRows).map(row => {
        return {
          original_url: row.querySelector('.ai-link-url').value.trim(),
          title: row.querySelector('.ai-link-title').value.trim(),
          custom_code: row.querySelector('.ai-link-code').value.trim() || null
        };
      }).filter(l => l.original_url);
      
      if (linksToCreate.length === 0) continue; // Skip empty project
      
      try {
        const createdProject = await ProjectsAPI.create({ name, description: desc, color });
        projSuccessCount++;
        
        for (const l of linksToCreate) {
           try {
              await LinksAPI.create(createdProject.id, {
                 original_url: l.original_url, 
                 title: l.title,
                 short_code: l.custom_code
              });
           } catch(linkErr) {
              console.error("Failed to create link:", linkErr);
              failedCount++;
           }
        }
      } catch(projErr) {
        console.error("Failed to create project:", projErr);
        failedCount += linksToCreate.length;
      }
    }
    
    if (projSuccessCount === 0 && failedCount > 0) {
      throw new Error("Failed to create any projects.");
    }
    
    Modal.hide();
    if (failedCount > 0) {
        Toast.error(`Created ${projSuccessCount} project(s), but ${failedCount} links or projects failed to save.`);
    } else {
        Toast.success(`Successfully created ${projSuccessCount} project(s)!`);
    }
    renderDashboard();
    
  } catch(err) {
    errEl.textContent = err.message || "An error occurred creating the campaign.";
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Confirm & Create';
  }
}

window.updateRowUrL = function(input) {
  const row = input.closest('.ai-link-row');
  const urlInput = row.querySelector('.ai-link-url');
  let currentVal = urlInput.value.trim();
  if (!currentVal) return;
  
  let tempVal = currentVal;
  if (!tempVal.startsWith('http')) tempVal = 'https://' + tempVal;
  
  try {
    const url = new URL(tempVal);
    const source = row.querySelector('.ai-utm-source').value.trim();
    const medium = row.querySelector('.ai-utm-medium').value.trim();
    const camp = row.querySelector('.ai-utm-campaign').value.trim();
    
    if (source) url.searchParams.set('utm_source', source); else url.searchParams.delete('utm_source');
    if (medium) url.searchParams.set('utm_medium', medium); else url.searchParams.delete('utm_medium');
    if (camp)   url.searchParams.set('utm_campaign', camp); else url.searchParams.delete('utm_campaign');
    
    let finalUrl = url.toString();
    if (!currentVal.startsWith('http')) finalUrl = finalUrl.replace(/^https?:\/\//, '');
    urlInput.value = finalUrl;
  } catch(e) {}
};

window.syncUtmInputsFromUrl = function(input) {
  const row = input.closest('.ai-link-row');
  try {
     let tempVal = input.value.trim();
     if (!tempVal) return;
     if (!tempVal.startsWith('http')) tempVal = 'https://' + tempVal;
     const url = new URL(tempVal);
     row.querySelector('.ai-utm-source').value = url.searchParams.get('utm_source') || '';
     row.querySelector('.ai-utm-medium').value = url.searchParams.get('utm_medium') || '';
     row.querySelector('.ai-utm-campaign').value = url.searchParams.get('utm_campaign') || '';
  } catch(e) {}
};
