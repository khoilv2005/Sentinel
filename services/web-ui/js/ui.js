export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

export function esc(value) {
  return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

export function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export function ago(value) {
  if (!value) return 'never';
  const seconds = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function bytes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  let n = Number(value), i = 0;
  const units = ['B','KB','MB','GB','TB','PB'];
  while (Math.abs(n) >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2)} ${units[i]}`;
}

export function duration(seconds) {
  if (seconds === null || seconds === undefined) return '—';
  let s = Math.max(0, Number(seconds));
  const d = Math.floor(s / 86400); s %= 86400;
  const h = Math.floor(s / 3600); s %= 3600;
  const m = Math.floor(s / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

export function badge(value, label = null) {
  const normalized = String(value || 'unknown').toLowerCase();
  return `<span class="badge ${esc(normalized)}">${esc(label ?? normalized)}</span>`;
}

export function state(value) {
  const normalized = String(value || 'unknown').toLowerCase();
  return `<span><span class="state-dot ${esc(normalized)}"></span>${esc(normalized)}</span>`;
}

export function statCard(label, value, detail, tone = '') {
  return `<div class="stat-card ${esc(tone)}"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-detail">${esc(detail || '')}</div></div>`;
}

export function empty(message) { return `<div class="empty">${esc(message)}</div>`; }

export function toast(message, error = false) {
  const root = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.className = `toast${error ? ' error' : ''}`;
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

export function openModal(title, subtitle, html) {
  const dialog = document.getElementById('modal');
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-subtitle').textContent = subtitle || '';
  document.getElementById('modal-body').innerHTML = html;
  dialog.showModal();
  return dialog;
}

export function closeModal() {
  const dialog = document.getElementById('modal');
  if (dialog.open) dialog.close();
}

export function metricValue(value, unit = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  return `${n.toFixed(n >= 100 ? 0 : 1)}${unit}`;
}

export function lineChart(series, { height = 180, unit = '', max = null } = {}) {
  const raw = (series || []).flatMap(item => item.values || []);
  if (!raw.length) return `<div class="chart-empty">No historical data available yet.</div>`;
  const points = raw.map(([ts, value]) => [Number(ts), Number(value)]).filter(([,v]) => Number.isFinite(v));
  if (!points.length) return `<div class="chart-empty">No historical data available yet.</div>`;
  const width = 800;
  const padX = 28, padY = 18;
  const minTs = Math.min(...points.map(p => p[0]));
  const maxTs = Math.max(...points.map(p => p[0]));
  const values = points.map(p => p[1]);
  const minVal = Math.min(0, ...values);
  const maxVal = max ?? Math.max(...values, 1);
  const range = Math.max(1e-9, maxVal - minVal);
  const x = ts => padX + ((ts - minTs) / Math.max(1, maxTs - minTs)) * (width - padX * 2);
  const y = v => height - padY - ((v - minVal) / range) * (height - padY * 2);
  const path = points.map((p,i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(' ');
  const area = `${path} L${x(points[points.length-1][0]).toFixed(1)},${height-padY} L${x(points[0][0]).toFixed(1)},${height-padY} Z`;
  const ticks = [0,.25,.5,.75,1].map(f => {
    const yy = padY + f * (height - padY * 2);
    const label = (maxVal - f * range).toFixed(maxVal > 100 ? 0 : 1);
    return `<line x1="${padX}" y1="${yy}" x2="${width-padX}" y2="${yy}"></line><text x="2" y="${yy+3}" fill="#667e8f" font-size="9">${label}${esc(unit)}</text>`;
  }).join('');
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="metric history"><g class="chart-grid">${ticks}</g><path class="chart-area" d="${area}"></path><path class="chart-path" d="${path}"></path></svg>`;
}

export function topologyHtml(graph) {
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  if (!nodes.length) return `<div class="empty">No devices are available for topology visualization.</div>`;
  const width = 1000, height = 560;
  const centerX = width / 2, centerY = height / 2;
  const radius = Math.min(width, height) * .37;
  const positions = {};
  nodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index / Math.max(1, nodes.length)) - Math.PI / 2;
    positions[node.id] = { x: centerX + radius * Math.cos(angle), y: centerY + radius * Math.sin(angle) };
  });
  const lines = edges.map(edge => {
    const a = positions[edge.source], b = positions[edge.target];
    return a && b ? `<line class="topology-edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"></line>` : '';
  }).join('');
  const nodeHtml = nodes.map(node => {
    const p = positions[node.id];
    const severity = node.severity || '';
    return `<button class="topology-node ${esc(severity)}" data-host-id="${esc(node.id)}" style="left:${(p.x/width)*100}%;top:${(p.y/height)*100}%"><span class="node-state ${esc(node.state)}"></span><strong>${esc(node.label)}</strong><span>${esc(node.ip)} · ${esc(node.device_class || 'unknown')}</span><span>${esc(node.site || 'default')}</span></button>`;
  }).join('');
  return `<div class="topology-stage"><svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">${lines}</svg>${nodeHtml}</div>`;
}
