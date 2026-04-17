/* ─── views-links.js — Link table + Create/Update forms ──────── */

const EXPIRY_OPTIONS = [
  { value: 'never', label: 'Never expires' },
  { value: '1d',    label: '1 day' },
  { value: '7d',    label: '7 days' },
  { value: '30d',   label: '30 days' },
  { value: '90d',   label: '90 days' },
];

// ── Compare Mode state ─────────────────────────────────────────────
let _compareSet       = new Set();
let _compareProjectId = null;
let _compareMode      = false;

/** Enter compare mode — checkboxes appear, context bar slides in. */
function _enterCompareMode() {
  _compareMode = true;
  _compareSet.clear();
  document.getElementById('links-section')?.classList.add('compare-mode');
  _syncCompareBar();
}

/** Exit compare mode — clean up all visual state. */
function _exitCompareMode() {
  _compareMode = false;
  _compareSet.clear();
  document.getElementById('links-section')?.classList.remove('compare-mode');
  // Uncheck every checkbox
  document.querySelectorAll('.cmp-cb').forEach(cb => { cb.checked = false; });
  _syncCompareBar();
}

/** Toggle a single link in/out of the selection set. */
function _toggleLinkSelect(linkId) {
  const cb = document.getElementById(`cb-${linkId}`);
  if (_compareSet.has(linkId)) {
    _compareSet.delete(linkId);
    if (cb) cb.checked = false;
  } else {
    if (_compareSet.size >= 4) {
      Toast.info('You can compare up to 4 links at a time.');
      if (cb) cb.checked = false;
      return;
    }
    _compareSet.add(linkId);
  }
  _syncCompareBar();
}

/** Update the floating context bar with the current selection count. */
function _syncCompareBar() {
  const bar     = document.getElementById('compare-bar');
  const cntEl   = document.getElementById('compare-count');
  const goBtn   = document.getElementById('compare-go-btn');
  if (!bar) return;

  if (!_compareMode) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';

  const n = _compareSet.size;
  cntEl.textContent = n === 0
    ? 'Select 2–4 links to compare'
    : `${n} link${n !== 1 ? 's' : ''} selected`;
  goBtn.disabled = n < 2;
  goBtn.textContent = n >= 2 ? `Compare ${n} Links` : 'Compare';
}

/** Run the comparison and auto-exit compare mode. */
function _runComparison() {
  const ids = [..._compareSet];
  if (ids.length < 2) return;
  _exitCompareMode();
  if (typeof showComparisonModal === 'function') {
    showComparisonModal(_compareProjectId, ids);
  } else {
    Toast.error('Comparison module not loaded. Please refresh and try again.');
  }
}

function renderLinksSection(project) {
  // Reset selection whenever a project detail page loads
  _compareSet.clear();
  _compareProjectId = project.id;

  const section = document.getElementById('links-section');
  section.innerHTML = `
    <div class="section-header">
      <span class="section-title">Links</span>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn btn--ghost btn--sm" onclick="_enterCompareMode()" id="enter-compare-btn"
                style="gap:5px">
          ⚡ Compare
        </button>
        ${project.is_active
          ? `<button class="btn btn--primary btn--sm" id="new-link-btn">
               <svg class="icon"><use href="#ico-plus"/></svg> New Link
             </button>`
          : `<span class="badge badge--red">Project inactive — cannot add links</span>`}
      </div>
    </div>

    <!-- Compare mode context bar (hidden until user enters compare mode) -->
    <div id="compare-bar" class="compare-bar" style="display:none">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:13px;font-weight:600;color:var(--accent)">⚡ Compare Mode</span>
        <span style="font-size:12.5px;color:var(--text-muted)" id="compare-count">Select 2–4 links to compare</span>
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn--primary btn--sm" id="compare-go-btn" disabled onclick="_runComparison()">Compare</button>
        <button class="btn btn--ghost btn--sm" onclick="_exitCompareMode()">Cancel</button>
      </div>
    </div>

    ${project.is_active ? renderCreateLinkForm(project.id) : ''}
    <div id="links-table-wrap">
      <div class="empty-state"><div class="skeleton" style="height:160px;width:100%"></div></div>
    </div>`;

  if (project.is_active) {
    document.getElementById('new-link-btn').onclick = () => {
      const formWrap = document.getElementById('create-link-form-wrap');
      formWrap.style.display = formWrap.style.display === 'none' ? 'block' : 'none';
    };
  }
  loadLinksTable(project.id);
}

window.computeManualUtm = function() {
  const urlInput = document.getElementById('lf-url');
  let currentVal = urlInput.value.trim();
  const preview = document.getElementById('lf-url-preview');
  if (!currentVal) {
     preview.textContent = 'Preview URL will appear here...';
     return;
  }
  let tempVal = currentVal;
  if (!tempVal.startsWith('http')) tempVal = 'https://' + tempVal;
  
  try {
     const url = new URL(tempVal);
     const src = document.getElementById('lf-utm-source').value.trim();
     const med = document.getElementById('lf-utm-medium').value.trim();
     const cmp = document.getElementById('lf-utm-campaign').value.trim();
     const trm = document.getElementById('lf-utm-term').value.trim();
     const cnt = document.getElementById('lf-utm-content').value.trim();
     
     if (src) url.searchParams.set('utm_source', src); else url.searchParams.delete('utm_source');
     if (med) url.searchParams.set('utm_medium', med); else url.searchParams.delete('utm_medium');
     if (cmp) url.searchParams.set('utm_campaign', cmp); else url.searchParams.delete('utm_campaign');
     if (trm) url.searchParams.set('utm_term', trm); else url.searchParams.delete('utm_term');
     if (cnt) url.searchParams.set('utm_content', cnt); else url.searchParams.delete('utm_content');
     
     let finalStr = url.toString();
     // visual preview keeps exactly what user saw (e.g. missing http)
     if (!currentVal.startsWith('http')) finalStr = finalStr.replace(/^https?:\/\//, '');
     preview.textContent = finalStr;
     window._lastComputedManualUrl = url.toString(); // API needs full valid URL
  } catch(e) {
     preview.textContent = 'Invalid URL format';
  }
};

function renderCreateLinkForm(projectId) {
  return `
    <div id="create-link-form-wrap" class="card mb-24" style="display:none">
      <h3 style="font-size:15px;font-weight:700;margin-bottom:16px">Create Short Link</h3>
      <form id="create-link-form">
        <div class="form-group" style="margin-bottom:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
             <label style="margin:0">Destination URL</label>
             <button type="button" class="btn btn--ghost btn--sm" style="padding: 2px 6px; font-size:11px;" onclick="document.getElementById('lf-utm-drawer').style.display = document.getElementById('lf-utm-drawer').style.display === 'none' ? 'block' : 'none'">[+] Add UTM Parameters</button>
          </div>
          <input id="lf-url" type="url" placeholder="https://example.com/very/long/path" required oninput="computeManualUtm()"/>
        </div>
        <div id="lf-utm-drawer" style="display:none; padding:12px; background:var(--bg-inset); border:1px dashed var(--border-color); border-radius:6px; margin-bottom:16px;">
           <span style="display:block; font-size:12px; font-weight:600; margin-bottom:8px; color:var(--text-muted)">UTM Builder</span>
           <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
              <input id="lf-utm-source" type="text" placeholder="utm_source (e.g. google)" oninput="computeManualUtm()"/>
              <input id="lf-utm-medium" type="text" placeholder="utm_medium (e.g. cpc)" oninput="computeManualUtm()"/>
              <input id="lf-utm-campaign" type="text" placeholder="utm_campaign (e.g. summer_sale)" oninput="computeManualUtm()"/>
              <input id="lf-utm-term" type="text" placeholder="utm_term" oninput="computeManualUtm()"/>
              <input id="lf-utm-content" type="text" placeholder="utm_content" style="grid-column: span 2" oninput="computeManualUtm()"/>
           </div>
           <div style="margin-top:10px; font-size:12px; color:var(--text-muted); font-family:monospace; word-break:break-all; background:#0f172a; padding:6px 8px; border-radius:4px;" id="lf-url-preview">Preview URL will appear here...</div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Custom Code <span style="font-weight:400;color:var(--text-muted)">(optional)</span></label>
            <input id="lf-code" type="text" placeholder="my-link" maxlength="20" pattern="[a-zA-Z0-9\\-]+"/>
            <span class="form-hint">4–20 chars, letters, numbers, hyphens only.</span>
          </div>
          <div class="form-group">
            <label>Expiry</label>
            <select id="lf-expiry">
              ${EXPIRY_OPTIONS.map(o=>`<option value="${o.value}">${o.label}</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="form-group">
          <label>Title <span style="font-weight:400;color:var(--text-muted)">(optional)</span></label>
          <input id="lf-title" type="text" placeholder="Descriptive title" maxlength="255"/>
        </div>
        <div id="lf-err" class="form-error mb-16" style="display:none"></div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button type="button" class="btn btn--ghost" onclick="document.getElementById('create-link-form-wrap').style.display='none'">Cancel</button>
          <button type="submit" class="btn btn--primary" id="lf-submit">Create Link</button>
        </div>
      </form>
    </div>`;
}

async function loadLinksTable(projectId, page = 1) {
  const wrap = document.getElementById('links-table-wrap');
  try {
    const data = await LinksAPI.list(projectId, page, 20);
    renderLinksTable(wrap, data, projectId, page);
  } catch(err) {
    wrap.innerHTML = `<div class="empty-state"><svg class="icon"><use href="#ico-alert"/></svg><h3>Failed to load links</h3><p>${err.message}</p></div>`;
  }        
  // Bind create form
  const form = document.getElementById('create-link-form');
  if (form) {
    form.onsubmit = async e => {
      e.preventDefault();
      const btn = document.getElementById('lf-submit');
      const errEl = document.getElementById('lf-err');
      errEl.style.display = 'none';
      btn.disabled = true; btn.textContent = 'Creating…';
      const custom = document.getElementById('lf-code').value.trim();
      
      let finalUrl = document.getElementById('lf-url').value.trim();
      if (document.getElementById('lf-utm-drawer').style.display !== 'none' && window._lastComputedManualUrl) {
         finalUrl = window._lastComputedManualUrl;
      }
      
      const body = {
        original_url: finalUrl,
        expiry: document.getElementById('lf-expiry').value,
        title: document.getElementById('lf-title').value.trim() || null,
      };
      if (custom) body.custom_code = custom;
      try {
        await LinksAPI.create(projectId, body);
        Toast.success('Link created!');
        document.getElementById('create-link-form-wrap').style.display = 'none';
        form.reset();
        loadLinksTable(projectId);
      } catch(err) {
        errEl.textContent = err.message; errEl.style.display = 'block';
      } finally {
        btn.disabled = false; btn.textContent = 'Create Link';
      }
    };
  }
}

function renderLinksTable(container, data, projectId, page) {
  const { links, total, per_page } = data;
  if (!links.length) {
    container.innerHTML = `<div class="empty-state">
      <svg class="icon"><use href="#ico-link"/></svg>
      <h3>No links yet</h3>
      <p>Click "New Link" above to create your first short link.</p></div>`;
    return;
  }
  const totalPages = Math.ceil(total / per_page);
  container.innerHTML = `
    <div class="table-wrapper">
      <table>
        <thead>
          <tr>
            <th class="cmp-col" style="width:36px;padding-right:0"></th>
            <th>Short Code</th>
            <th>Destination</th>
            <th>Title</th>
            <th>Clicks</th>
            <th>Created</th>
            <th>Expires</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${links.map(l => linkRow(l, projectId)).join('')}
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <span class="pagination-info">${total} total · Page ${page} / ${totalPages}</span>
      <div class="pagination-btns">
        <button class="btn btn--ghost btn--sm" ${page<=1?'disabled':''} onclick="loadLinksTable('${projectId}',${page-1})">
          <svg class="icon"><use href="#ico-chevron-left"/></svg> Prev
        </button>
        <button class="btn btn--ghost btn--sm" ${page>=totalPages?'disabled':''} onclick="loadLinksTable('${projectId}',${page+1})">
          Next <svg class="icon"><use href="#ico-chevron-right"/></svg>
        </button>
      </div>
    </div>`;
}

function linkRow(l, projectId) {
  const shortUrl = l.short_url;
  const expires  = l.expires_at ? new Date(l.expires_at).toLocaleDateString() : '—';
  const expired  = l.expires_at && new Date(l.expires_at) < new Date();
  return `<tr id="link-row-${l.id}">
    <td class="cmp-col" style="width:36px;padding-right:0;padding-left:14px">
      <input type="checkbox" class="cmp-cb" id="cb-${l.id}"
             ${_compareSet.has(l.id) ? 'checked' : ''}
             onchange="_toggleLinkSelect('${l.id}')"
             style="width:15px;height:15px;cursor:pointer;accent-color:var(--accent)">
    </td>
    <td>
      <div class="short-code-cell">
        <span class="short-code">${escHtml(l.short_code)}</span>
        <button class="copy-btn" onclick="copyText('${shortUrl}',this)" title="Copy short URL">
          <svg class="icon"><use href="#ico-copy"/></svg>
        </button>
        <a href="${shortUrl}" target="_blank" title="Open">
          <svg class="icon" style="color:var(--text-muted)"><use href="#ico-external"/></svg>
        </a>
      </div>
    </td>
    <td><span class="link-url" title="${escHtml(l.original_url)}">${escHtml(l.original_url)}</span></td>
    <td style="color:var(--text-muted)">${l.title ? escHtml(l.title) : '—'}</td>
    <td><span class="badge badge--blue">${fmtNum(l.click_count)}</span></td>
    <td class="text-muted text-sm">${fmtDate(l.created_at)}</td>
    <td><span class="${expired?'badge badge--red':'text-muted'}">${expires}</span></td>
    <td>
      <span class="badge ${expired ? 'badge--red' : (l.is_active?'badge--green':'badge--gray')}">
        ${expired ? 'Expired' : (l.is_active ? 'Active' : 'Inactive')}
      </span>
    </td>
    <td>
      <div class="table-actions">
        <button class="btn btn--ghost btn--icon btn--sm" title="Analytics"
          onclick="showLinkAnalytics('${projectId}','${l.id}')">
          <svg class="icon"><use href="#ico-bar-chart"/></svg>
        </button>
        <button class="btn btn--ghost btn--icon btn--sm" title="Edit title"
          onclick="showEditLinkModal('${projectId}','${l.id}','${escHtml(l.title||'')}')">
          <svg class="icon"><use href="#ico-edit"/></svg>
        </button>
        <button class="btn btn--ghost btn--icon btn--sm" title="${l.is_active?'Deactivate':'Activate'}"
          onclick="toggleLinkActive('${projectId}','${l.id}',${l.is_active})">
          <svg class="icon"><use href="${l.is_active?'#ico-toggle-on':'#ico-toggle-off'}"/></svg>
        </button>
        <button class="btn btn--ghost btn--icon btn--sm" title="Delete"
          onclick="confirmDeleteLink('${projectId}','${l.id}','${escHtml(l.short_code)}')">
          <svg class="icon" style="color:var(--danger)"><use href="#ico-trash"/></svg>
        </button>
      </div>
    </td>
  </tr>`;
}

async function toggleLinkActive(projectId, linkId, currentlyActive) {
  try {
    await LinksAPI.update(projectId, linkId, { is_active: !currentlyActive });
    Toast.success(currentlyActive ? 'Link deactivated.' : 'Link reactivated.');
    loadLinksTable(projectId);
  } catch(err) { Toast.error(err.message); }
}

function confirmDeleteLink(projectId, linkId, code) {
  Confirm.show(
    'Delete link?',
    `Short code /${code} will be permanently deleted. This cannot be undone.`,
    async () => {
      try {
        await LinksAPI.delete(projectId, linkId);
        Toast.success('Link deleted.');
        loadLinksTable(projectId);
      } catch(err) { Toast.error(err.message); }
    }
  );
}

function showEditLinkModal(projectId, linkId, currentTitle) {
  Modal.show('Edit Link', `
    <form id="edit-link-form">
      <div class="form-group" style="margin-bottom:20px">
        <label>Title</label>
        <input id="el-title" type="text" maxlength="255" placeholder="Descriptive title" value="${escHtml(currentTitle)}"/>
      </div>
      <div id="el-err" class="form-error mb-16" style="display:none"></div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button type="button" class="btn btn--ghost" onclick="Modal.hide()">Cancel</button>
        <button type="submit" class="btn btn--primary" id="el-submit">Save</button>
      </div>
    </form>`);

  document.getElementById('edit-link-form').onsubmit = async e => {
    e.preventDefault();
    const btn = document.getElementById('el-submit');
    const errEl = document.getElementById('el-err');
    errEl.style.display = 'none';
    btn.disabled = true; btn.textContent = 'Saving…';
    try {
      await LinksAPI.update(projectId, linkId, { title: document.getElementById('el-title').value.trim() || null });
      Modal.hide();
      Toast.success('Link updated.');
      loadLinksTable(projectId);
    } catch(err) {
      errEl.textContent = err.message; errEl.style.display = 'block';
    } finally {
      btn.disabled = false; btn.textContent = 'Save';
    }
  };
}
