/* ─── views-analytics.js — Link analytics modal + chart helpers ─ */

const DONUT_COLORS = ['#6366f1','#8b5cf6','#ec4899','#10b981','#f59e0b','#3b82f6','#ef4444','#06b6d4'];

async function showLinkAnalytics(projectId, linkId) {
  Modal.show('Link Analytics', `<div style="height:200px" class="skeleton"></div>`, 'modal-box--lg');
  try {
    const a = await LinksAPI.analytics(projectId, linkId);
    Modal.setContent(buildAnalyticsContent(a));
    renderTimelineChart('timeline-canvas-link', a.clicks_over_time || []);
  } catch(err) {
    Modal.setContent(`<p class="form-error" style="text-align:center;padding:24px">${err.message}</p>`);
  }
}

window.generateLinkInsights = async function(linkId, isRegenerate = false) {
  const inputEl = document.getElementById('ai-prompt-input');
  const btn = document.getElementById('btn-ai-ask');
  const container = document.getElementById('ai-insight-container');
  
  let prompt = inputEl ? inputEl.value.trim() : '';
  if (isRegenerate && window._lastAIPrompt !== undefined) {
    prompt = window._lastAIPrompt;
  } else {
    window._lastAIPrompt = prompt;
  }
  
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = 'Analyzing...';
  }
  
  container.style.display = 'block';
  container.innerHTML = '<div class="skeleton" style="height:60px"></div>';
  
  try {
    const res = await AIAPI.insights(linkId, prompt);
    const content = escHtml(res.insight).replace(/\n/g, '<br>');
    container.innerHTML = `
      <div style="margin-bottom:12px;">
        <p style="margin:0; font-size:14px; line-height:1.6; color:var(--text-primary)">${content}</p>
      </div>
      <div style="display:flex; gap:8px; justify-content:flex-end;">
        <button class="btn" style="background:transparent; border:1px solid var(--border-color); color:var(--text-secondary); padding:4px 10px; font-size:12px; border-radius:4px; cursor:pointer;" onclick="copyInsightText(this)">📋 Copy</button>
        <button class="btn" style="background:transparent; border:1px solid var(--border-color); color:var(--text-secondary); padding:4px 10px; font-size:12px; border-radius:4px; cursor:pointer;" onclick="generateLinkInsights('${linkId}', true)">🔄 Regenerate</button>
      </div>
    `;
  } catch(err) {
    container.innerHTML = `
      <p class="form-error" style="margin:0; margin-bottom:12px;">${err.message}</p>
      <div style="display:flex; justify-content:flex-end;">
        <button class="btn" style="background:transparent; border:1px solid var(--border-color); color:var(--text-secondary); padding:4px 10px; font-size:12px; border-radius:4px; cursor:pointer;" onclick="generateLinkInsights('${linkId}', true)">🔄 Try Again</button>
      </div>
    `;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = 'Ask';
    }
  }
};

window.copyInsightText = function(btn) {
  const container = btn.parentElement.previousElementSibling;
  const text = container.innerText;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✅ Copied!';
    setTimeout(() => btn.innerHTML = orig, 2000);
  });
};

function buildAnalyticsContent(a) {
  return `
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h2 class="modal-title" style="margin:0;">
        <span class="text-mono" style="color:var(--accent-light)">/${escHtml(a.short_code)}</span>
        — Analytics
      </h2>
    </div>
    
    <!-- AI Analysis Section -->
    <div id="ai-chat-section" style="margin-top:20px; padding:16px; background:var(--bg-card); border:1px solid rgba(99,102,241,0.3); border-radius:8px;">
      <h3 style="margin-top:0; font-size:14px; font-weight:600; color:var(--accent-light); margin-bottom:12px;">✨ Ask AI Analyst</h3>
      <div style="display:flex; gap:8px;">
        <input type="text" id="ai-prompt-input" placeholder="Ask a specific question (e.g., 'What was the peak hour yesterday?')" style="flex:1; padding:8px 12px; border-radius:6px; background:var(--bg-base); border:1px solid var(--border-color); color:var(--text-primary);" onkeydown="if(event.key==='Enter') generateLinkInsights('${a.link_id || a.id}')">
        <button class="btn" style="background:var(--accent-primary); color:#fff; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; font-weight:600;" onclick="generateLinkInsights('${a.link_id || a.id}')" id="btn-ai-ask">Ask</button>
      </div>
      <div id="ai-insight-container" style="display:none; margin-top:16px; padding:16px; background:rgba(99,102,241,0.05); border-radius:6px; border:1px solid rgba(99,102,241,0.15);"></div>
    </div>

    <div class="stats-strip" style="margin-top:24px;">
      ${statBox(a.total_clicks, 'Total Clicks')}
      ${statBox(a.human_clicks, 'Human Clicks')}
      ${statBox(a.unique_visitors, 'Unique IPs')}
      ${statBox(a.clicks_today, 'Today')}
      ${statBox(a.clicks_this_week, 'This Week')}
      ${statBox(a.clicks_this_month, 'This Month')}
    </div>
    ${a.bot_clicks > 0 ? `<div class="mb-16" style="padding:10px 14px;border-radius:8px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);font-size:12.5px;color:#fbbf24">
      ⚠ ${a.bot_clicks} bot click${a.bot_clicks>1?'s':''} detected and excluded from human totals.
    </div>` : ''}
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
    <div class="chart-box">
      <div class="chart-title">Clicks — Last 30 Days</div>
      ${timelineChart(a.clicks_over_time||[], 'timeline-canvas-link')}
    </div>
    ${a.peak_hour !== null && a.peak_hour !== undefined ? `
    <p class="text-sm text-muted" style="margin-top:12px;text-align:center">
      Peak hour: <strong style="color:var(--text-primary)">${formatHour(a.peak_hour)}</strong>
    </p>` : ''}`;
}

// ── Chart helpers ─────────────────────────────────────────────
function donutChart(data) {
  if (!data || !Object.keys(data).length) return '<p class="text-muted text-sm" style="text-align:center;padding:20px">No data</p>';
  const entries = Object.entries(data).sort((a,b)=>b[1]-a[1]);
  const total = entries.reduce((s,[,v])=>s+v,0);
  if (!total) return '<p class="text-muted text-sm" style="text-align:center;padding:20px">No data</p>';

  const r = 54, cx = 64, cy = 64, stroke = 18;
  const circumference = 2 * Math.PI * r;
  let offset = 0;
  const segments = entries.map(([k,v],i) => {
    const pct = v / total;
    const dash = pct * circumference;
    const seg = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none"
      stroke="${DONUT_COLORS[i%DONUT_COLORS.length]}"
      stroke-width="${stroke}"
      stroke-dasharray="${dash} ${circumference - dash}"
      stroke-dashoffset="${-offset}"
      transform="rotate(-90 ${cx} ${cy})"
      style="transition:stroke-dasharray 0.5s ease"/>`;
    offset += dash;
    return seg;
  });

  const legend = entries.map(([k,v],i) => `
    <div class="donut-legend-item">
      <span class="legend-dot" style="background:${DONUT_COLORS[i%DONUT_COLORS.length]}"></span>
      <span class="legend-label">${escHtml(k||'unknown')}</span>
      <span class="legend-val">${v}</span>
    </div>`).join('');

  return `<div class="donut-wrap">
    <svg class="donut-svg" viewBox="0 0 128 128" width="100" height="100">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg-base)" stroke-width="${stroke}"/>
      ${segments.join('')}
      <text x="${cx}" y="${cy+5}" text-anchor="middle" fill="var(--text-primary)" font-size="13" font-weight="700">${total}</text>
    </svg>
    <div class="donut-legend">${legend}</div>
  </div>`;
}

function barChart(data, isReferer = false) {
  if (!data || !Object.keys(data).length) return '<p class="text-muted text-sm" style="text-align:center;padding:20px">No data</p>';
  const entries = Object.entries(data).sort((a,b)=>b[1]-a[1]).slice(0, 8);
  const max = entries[0]?.[1] || 1;
  return `<div class="bar-chart">
    ${entries.map(([k,v]) => `
      <div class="bar-row">
        <span class="bar-label" title="${escHtml(k||'unknown')}">${escHtml(k||'unknown')}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width:${Math.round((v/max)*100)}%"></div>
        </div>
        <span class="bar-val">${v}</span>
      </div>`).join('')}
  </div>`;
}

function timelineChart(data, canvasId = 'timeline-canvas') {
  if (!data || !data.length) return '<p class="text-muted text-sm" style="text-align:center;padding:20px">No data</p>';
  return `<div style="height:180px;position:relative"><canvas id="${canvasId}"></canvas></div>`;
}

function renderTimelineChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !window.Chart) return;
  
  new window.Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.map(d => new Date(d.date).toLocaleDateString(undefined, {month:'short', day:'numeric'})),
      datasets: [{
        label: 'Clicks',
        data: data.map(d => d.clicks),
        backgroundColor: '#6366f1',
        hoverBackgroundColor: '#818cf8',
        borderRadius: 4,
        borderSkipped: false,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(26,29,53,0.95)',
          titleColor: '#f1f5f9',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(99,102,241,0.3)',
          borderWidth: 1,
          padding: 12,
          displayColors: false,
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 10 } },
        y: { 
          grid: { color: 'rgba(148,163,184,0.1)' }, 
          border: { display: false }, 
          ticks: { color: '#94a3b8', beginAtZero: true, precision: 0 } 
        }
      }
    }
  });
}

// ── Stat box helper ───────────────────────────────────────────
function statBox(val, lbl) {
  return `<div class="stat-box">
    <div class="stat-box-val">${fmtNum(val??0)}</div>
    <div class="stat-box-lbl">${lbl}</div>
  </div>`;
}

function formatHour(h) {
  if (h === null || h === undefined) return '—';
  const ampm = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 || 12;
  return `${h12}:00 ${ampm}`;
}
