/* ─── views-comparison.js — Link Comparison Dashboard + AI ───── */

const COMPARE_COLORS       = ['#6366f1', '#ec4899', '#10b981', '#f59e0b'];
const COMPARE_COLORS_ALPHA = ['rgba(99,102,241,0.12)', 'rgba(236,72,153,0.12)', 'rgba(16,185,129,0.12)', 'rgba(245,158,11,0.12)'];

let _comparisonCharts = [];

function _destroyComparisonCharts() {
  _comparisonCharts.forEach(c => { try { c.destroy(); } catch (_) {} });
  _comparisonCharts = [];
}

// ── Helpers ───────────────────────────────────────────────────────

function _computeTrend(clicksOverTime) {
  if (!clicksOverTime || clicksOverTime.length < 6) return null;
  const mid        = Math.floor(clicksOverTime.length / 2);
  const firstHalf  = clicksOverTime.slice(0, mid).reduce((s, d) => s + d.clicks, 0);
  const secondHalf = clicksOverTime.slice(mid).reduce((s, d) => s + d.clicks, 0);
  if (firstHalf === 0) return { dir: secondHalf > 0 ? 'up' : 'flat', pct: null };
  const pct = Math.round((secondHalf - firstHalf) / firstHalf * 100);
  return { dir: pct > 5 ? 'up' : pct < -5 ? 'down' : 'flat', pct };
}

function _computeQualityScores(links) {
  return links.map(l => {
    const humanRatio  = l.total_clicks  > 0 ? l.human_clicks    / l.total_clicks  : 0;
    const uniqueRatio = l.human_clicks  > 0 ? l.unique_visitors / l.human_clicks  : 0;
    return Math.round(humanRatio * 50 + uniqueRatio * 50);
  });
}

function _trendLabel(t) {
  if (!t) return { text: '— ', color: 'var(--text-muted)' };
  if (t.dir === 'up')   return { text: `↑ ${t.pct !== null ? '+'+t.pct+'%' : 'Rising'}`,  color: '#4ade80' };
  if (t.dir === 'down') return { text: `↓ ${t.pct !== null ? t.pct+'%'   : 'Falling'}`, color: '#f87171' };
  return { text: '→ Stable', color: 'var(--text-muted)' };
}

// ── Entry point ───────────────────────────────────────────────────

async function showComparisonModal(projectId, linkIds) {
  _destroyComparisonCharts();
  Modal.show('', `<div style="height:320px" class="skeleton"></div>`, 'modal-box--xl');

  try {
    const allData = await Promise.all(
      linkIds.map(id => LinksAPI.analytics(projectId, id))
    );
    Modal.setContent(_buildComparisonDashboard(allData));
    _renderTimelineChart(allData);
    _renderGroupedBar(allData);
    _loadAIReport(linkIds);       // non-blocking — fills #compare-ai-body
  } catch (err) {
    Modal.setContent(
      `<p class="form-error" style="text-align:center;padding:32px">${escHtml(err.message)}</p>`
    );
  }
}

// ── Dashboard builder (pure HTML string) ─────────────────────────

function _buildComparisonDashboard(links) {
  const trends        = links.map(l => _computeTrend(l.clicks_over_time || []));
  const qualityScores = _computeQualityScores(links);
  const redFlagsHTML  = _buildRedFlagsHTML(links, trends);

  return `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:20px;flex-wrap:wrap">
      <h2 class="modal-title" style="margin:0">Link Comparison</h2>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${links.map((l, i) => `
          <span style="display:inline-flex;align-items:center;gap:5px;padding:3px 12px;
                       border-radius:999px;background:${COMPARE_COLORS_ALPHA[i]};
                       border:1px solid ${COMPARE_COLORS[i]}55;font-size:12px;
                       font-weight:600;color:${COMPARE_COLORS[i]}">
            <span style="width:8px;height:8px;border-radius:50%;background:${COMPARE_COLORS[i]}"></span>
            /${escHtml(l.short_code)}
          </span>`).join('')}
      </div>
    </div>

    ${redFlagsHTML}
    ${_buildScorecardHTML(links, trends)}

    <div class="chart-section" style="margin-top:20px">
      <div class="chart-box" style="grid-column:1/-1">
        <div class="chart-title">Traffic Over Time — Last 30 Days</div>
        <div style="height:200px;position:relative"><canvas id="cmp-timeline"></canvas></div>
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-box">
        <div class="chart-title">Volume by Period</div>
        <div style="height:180px;position:relative"><canvas id="cmp-periods"></canvas></div>
      </div>
      <div class="chart-box">
        <div class="chart-title">Quality Score</div>
        ${_buildQualityHTML(links, qualityScores)}
      </div>
    </div>

    <div class="chart-section">
      <div class="chart-box">
        <div class="chart-title">Device Profile</div>
        ${_buildDeviceHTML(links)}
      </div>
      <div class="chart-box">
        <div class="chart-title">Top Traffic Source</div>
        ${_buildReferrerHTML(links)}
      </div>
    </div>

    <div style="margin-top:24px;padding-top:20px;border-top:1px solid var(--border)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        <span style="font-size:15px;font-weight:700">✨ AI Analysis Report</span>
        <span class="text-sm text-muted">— winners &amp; underperformers</span>
      </div>
      <div id="compare-ai-body">
        <div class="skeleton" style="height:130px;border-radius:8px"></div>
      </div>
    </div>
  `;
}

// ── Scoreboard ────────────────────────────────────────────────────

function _buildScorecardHTML(links, trends) {
  const METRICS = [
    { label: 'Total Clicks',  val: l => l.total_clicks,      fmt: fmtNum },
    { label: 'Human Clicks',  val: l => l.human_clicks,      fmt: fmtNum },
    { label: 'Unique IPs',    val: l => l.unique_visitors,   fmt: fmtNum },
    { label: 'This Week',     val: l => l.clicks_this_week,  fmt: fmtNum },
    { label: 'This Month',    val: l => l.clicks_this_month, fmt: fmtNum },
    { label: 'Bot Rate',      val: l => l.total_clicks > 0 ? Math.round(l.bot_clicks / l.total_clicks * 1000) / 10 : 0,
                              fmt: v => v + '%', lowerBetter: true },
    { label: 'Unique Ratio',  val: l => l.human_clicks > 0 ? Math.round(l.unique_visitors / l.human_clicks * 100) / 100 : 0,
                              fmt: v => v.toFixed(2) },
  ];

  const metricRows = METRICS.map(m => {
    const vals    = links.map(m.val);
    const allSame = vals.every(v => v === vals[0]);
    const bestVal = m.lowerBetter ? Math.min(...vals) : Math.max(...vals);
    const worstVal= m.lowerBetter ? Math.max(...vals) : Math.min(...vals);

    return `<tr>
      <td style="padding:10px 14px;font-size:11.5px;font-weight:600;color:var(--text-muted);white-space:nowrap">${m.label}</td>
      ${links.map((l, i) => {
        const v       = m.val(l);
        const isBest  = !allSame && v === bestVal;
        const isWorst = !allSame && v === worstVal;
        return `<td style="padding:10px 14px;text-align:center">
          <span style="font-size:13.5px;font-weight:${isBest ? 700 : 500};
                       color:${isBest ? '#4ade80' : isWorst ? '#f87171' : 'var(--text-primary)'}">
            ${m.fmt(v)}
          </span>
          ${isBest  ? '<span style="font-size:10px;margin-left:2px">⭐</span>' : ''}
          ${isWorst ? '<span style="font-size:10px;margin-left:2px;color:#f87171">▼</span>' : ''}
        </td>`;
      }).join('')}
    </tr>`;
  });

  const trendRow = `<tr>
    <td style="padding:10px 14px;font-size:11.5px;font-weight:600;color:var(--text-muted)">30d Trend</td>
    ${links.map((_, i) => {
      const { text, color } = _trendLabel(trends[i]);
      return `<td style="padding:10px 14px;text-align:center;font-size:12.5px;font-weight:600;color:${color}">${text}</td>`;
    }).join('')}
  </tr>`;

  return `
    <div class="chart-box">
      <div class="chart-title">Metrics at a Glance</div>
      <div class="table-wrapper" style="border:none">
        <table>
          <thead>
            <tr>
              <th style="min-width:110px">Metric</th>
              ${links.map((l, i) => `
                <th style="text-align:center">
                  <span style="font-family:monospace;color:${COMPARE_COLORS[i]}">/${escHtml(l.short_code)}</span>
                </th>`).join('')}
            </tr>
          </thead>
          <tbody>${metricRows.join('')}${trendRow}</tbody>
        </table>
      </div>
    </div>`;
}

// ── Red Flags ─────────────────────────────────────────────────────

function _buildRedFlagsHTML(links, trends) {
  const flags = [];
  links.forEach((l, i) => {
    const botPct = l.total_clicks > 0 ? Math.round(l.bot_clicks / l.total_clicks * 100) : 0;
    if (l.total_clicks === 0)
      flags.push(`⚠ <strong>/${l.short_code}</strong> has no traffic yet.`);
    else if (l.clicks_this_week === 0)
      flags.push(`⚠ <strong>/${l.short_code}</strong> — zero clicks in the past 7 days.`);
    if (botPct > 20)
      flags.push(`🤖 <strong>/${l.short_code}</strong> — ${botPct}% bot traffic (unusually high).`);
    const t = trends[i];
    if (t && t.dir === 'down' && t.pct !== null && t.pct < -25)
      flags.push(`↓ <strong>/${l.short_code}</strong> — traffic dropped ${Math.abs(t.pct)}% over 30 days.`);
  });

  if (!flags.length) return '';
  return `
    <div style="padding:12px 16px;border-radius:8px;background:rgba(239,68,68,0.08);
                border:1px solid rgba(239,68,68,0.22);margin-bottom:18px">
      <div style="font-size:12.5px;font-weight:700;color:#f87171;margin-bottom:6px">Issues Detected</div>
      <div style="display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:#fca5a5">
        ${flags.map(f => `<div>${f}</div>`).join('')}
      </div>
    </div>`;
}

// ── Quality Score ─────────────────────────────────────────────────

function _buildQualityHTML(links, scores) {
  return `
    <div style="display:flex;flex-direction:column;gap:14px;padding-top:4px">
      ${links.map((l, i) => {
        const s     = scores[i];
        const color = s >= 70 ? '#4ade80' : s >= 45 ? '#fbbf24' : '#f87171';
        return `<div>
          <div style="display:flex;justify-content:space-between;margin-bottom:5px">
            <span style="font-size:12px;font-family:monospace;font-weight:600;color:${COMPARE_COLORS[i]}">/${escHtml(l.short_code)}</span>
            <span style="font-size:13px;font-weight:700;color:${color}">${s}/100</span>
          </div>
          <div style="height:8px;border-radius:99px;background:var(--bg-base);overflow:hidden">
            <div style="height:100%;width:${s}%;background:${color};border-radius:99px;transition:width 0.7s ease"></div>
          </div>
        </div>`;
      }).join('')}
      <p class="text-sm text-muted" style="margin:0">Based on human ratio + unique visitor ratio</p>
    </div>`;
}

// ── Device Profile (mini stacked bars) ───────────────────────────

function _buildDeviceHTML(links) {
  const DCOLORS = { mobile: '#6366f1', desktop: '#10b981', tablet: '#f59e0b', bot: '#ef4444', unknown: '#64748b' };
  return `
    <div style="display:flex;flex-direction:column;gap:16px">
      ${links.map((l, i) => {
        const devs  = l.devices || {};
        const total = Object.values(devs).reduce((s, v) => s + v, 0);
        if (!total) return `<div style="font-size:12px;color:var(--text-muted)">/${escHtml(l.short_code)}: No data</div>`;

        const segs = Object.entries(devs)
          .sort((a, b) => b[1] - a[1])
          .map(([k, v]) => ({ k, pct: Math.round(v / total * 100) }))
          .filter(s => s.pct > 0);

        return `<div>
          <div style="font-size:12px;font-family:monospace;font-weight:600;color:${COMPARE_COLORS[i]};margin-bottom:5px">/${escHtml(l.short_code)}</div>
          <div style="display:flex;height:10px;border-radius:99px;overflow:hidden;gap:1px">
            ${segs.map(s => `<div title="${s.k}: ${s.pct}%" style="flex:${s.pct};background:${DCOLORS[s.k] || '#64748b'}"></div>`).join('')}
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:4px">
            ${segs.map(s => `<span class="text-sm text-muted">${s.k} ${s.pct}%</span>`).join('')}
          </div>
        </div>`;
      }).join('')}
    </div>`;
}

// ── Top Referrer ──────────────────────────────────────────────────

function _buildReferrerHTML(links) {
  return `
    <div style="display:flex;flex-direction:column;gap:12px">
      ${links.map((l, i) => {
        const refs    = l.referers || {};
        const entries = Object.entries(refs).sort((a, b) => b[1] - a[1]);
        const top     = entries[0];
        const total   = entries.reduce((s, [, v]) => s + v, 0);
        return `<div style="display:flex;align-items:flex-start;gap:10px">
          <span style="font-size:12px;font-family:monospace;font-weight:600;color:${COMPARE_COLORS[i]};min-width:80px;flex-shrink:0">/${escHtml(l.short_code)}</span>
          ${top
            ? `<div>
                <div style="font-size:13px;font-weight:600;color:var(--text-primary)">${escHtml(top[0])}</div>
                <div class="text-sm text-muted">${Math.round(top[1] / Math.max(total, 1) * 100)}% of traffic</div>
              </div>`
            : `<span class="text-sm text-muted">Direct / Unknown</span>`}
        </div>`;
      }).join('')}
    </div>`;
}

// ── Chart.js: Multi-line Timeline ─────────────────────────────────

function _renderTimelineChart(links) {
  const ctx = document.getElementById('cmp-timeline');
  if (!ctx || !window.Chart) return;

  const allDates = [...new Set(
    links.flatMap(l => (l.clicks_over_time || []).map(d => d.date))
  )].sort();

  const chart = new window.Chart(ctx, {
    type: 'line',
    data: {
      labels: allDates.map(d => new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })),
      datasets: links.map((l, i) => {
        const byDate = Object.fromEntries((l.clicks_over_time || []).map(d => [d.date, d.clicks]));
        return {
          label: '/' + l.short_code,
          data: allDates.map(d => byDate[d] ?? 0),
          borderColor: COMPARE_COLORS[i],
          backgroundColor: COMPARE_COLORS_ALPHA[i],
          borderWidth: 2,
          tension: 0.3,
          fill: false,
          pointRadius: 2,
          pointHoverRadius: 5,
        };
      }),
    },
    options: _chartOptions({ mode: 'index' }),
  });
  _comparisonCharts.push(chart);
}

// ── Chart.js: Grouped Bar by Period ──────────────────────────────

function _renderGroupedBar(links) {
  const ctx = document.getElementById('cmp-periods');
  if (!ctx || !window.Chart) return;

  const chart = new window.Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Today', 'This Week', 'This Month'],
      datasets: links.map((l, i) => ({
        label: '/' + l.short_code,
        data: [l.clicks_today, l.clicks_this_week, l.clicks_this_month],
        backgroundColor: COMPARE_COLORS[i],
        borderRadius: 4,
        borderSkipped: false,
      })),
    },
    options: _chartOptions(),
  });
  _comparisonCharts.push(chart);
}

// ── Shared Chart.js options ───────────────────────────────────────

function _chartOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: extra.mode || 'nearest', intersect: false },
    plugins: {
      legend: { position: 'top', labels: { color: '#94a3b8', font: { size: 11 }, boxWidth: 12, padding: 12 } },
      tooltip: {
        backgroundColor: 'rgba(19,21,42,0.97)',
        titleColor: '#f1f5f9',
        bodyColor: '#94a3b8',
        borderColor: 'rgba(99,102,241,0.3)',
        borderWidth: 1,
        padding: 12,
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#94a3b8', maxTicksLimit: 8 } },
      y: {
        grid: { color: 'rgba(148,163,184,0.07)' },
        border: { display: false },
        ticks: { color: '#94a3b8', beginAtZero: true, precision: 0 },
      },
    },
  };
}

// ── AI Report ─────────────────────────────────────────────────────

async function _loadAIReport(linkIds) {
  const container = document.getElementById('compare-ai-body');
  if (!container) return;
  try {
    const res     = await CompareAPI.insight(linkIds);
    const html    = escHtml(res.insight).replace(/\n\n/g, '</p><p style="margin-top:10px">').replace(/\n/g, '<br>');
    container.innerHTML = `
      <div style="padding:16px 20px;background:rgba(99,102,241,0.05);border:1px solid rgba(99,102,241,0.15);
                  border-radius:10px;line-height:1.8;font-size:13.5px;color:var(--text-primary)">
        <p style="margin:0">${html}</p>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">
        <button class="btn btn--ghost btn--sm" onclick="_copyCompareReport(this)">📋 Copy Report</button>
        <button class="btn btn--ghost btn--sm" onclick="_reloadCompareReport(${JSON.stringify(linkIds)})">🔄 Regenerate</button>
      </div>`;
  } catch (err) {
    container.innerHTML = `
      <p class="form-error" style="margin:0 0 10px">${escHtml(err.message)}</p>
      <button class="btn btn--ghost btn--sm" onclick="_reloadCompareReport(${JSON.stringify(linkIds)})">🔄 Try Again</button>`;
  }
}

function _copyCompareReport(btn) {
  const text = btn.closest('div').previousElementSibling.innerText;
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = '✅ Copied!';
    setTimeout(() => { btn.innerHTML = orig; }, 2000);
  });
}

function _reloadCompareReport(linkIds) {
  const c = document.getElementById('compare-ai-body');
  if (c) {
    c.innerHTML = `<div class="skeleton" style="height:130px;border-radius:8px"></div>`;
    _loadAIReport(linkIds);
  }
}
