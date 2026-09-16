import { api } from './api.js';
import { $, badge, empty, esc, fmtDate, toast } from './ui.js';

const root = $('#page-content');
let scheduled = false;
let running = false;

const ROUTE_GROUPS = {
  hosts: 'assets',
  host: 'assets',
  services: 'assets',
  topology: 'assets',
  discovery: 'assets',
  agentless: 'monitoring',
  agents: 'monitoring',
  credentials: 'monitoring',
  policies: 'monitoring',
  rules: 'alerts',
  notifications: 'alerts',
  maintenance: 'alerts',
};

const LEGACY_REDIRECTS = {
  devices: 'hosts',
  snmp: 'agentless',
  integrations: 'settings',
};

const GROUP_TABS = {
  assets: [
    ['hosts', 'All assets'],
    ['services', 'Services'],
    ['topology', 'Topology'],
    ['discovery', 'Discovery'],
  ],
  monitoring: [
    ['agentless', 'Remote methods'],
    ['agents', 'Managed Agent'],
    ['credentials', 'Credentials'],
    ['policies', 'Agent settings'],
  ],
  alerts: [
    ['rules', 'Rules'],
    ['notifications', 'Notifications'],
    ['maintenance', 'Maintenance'],
  ],
};

function routeName() {
  return (location.hash || '#overview').slice(1).split('/')[0];
}

function ensureStyles() {
  if (document.getElementById('sentinel-runtime-enhancement-style')) return;
  const style = document.createElement('style');
  style.id = 'sentinel-runtime-enhancement-style';
  style.textContent = `
    .badge.suppressed{background:#202936;border-color:#41526a;color:#a9c5e8}
    .badge.degraded{background:#332a14;border-color:#695823;color:#f0cd69}
    .delivery-error{max-width:420px;white-space:normal;overflow-wrap:anywhere}
    .unified-subnav{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px 0;padding:8px;border:1px solid var(--border);border-radius:10px;background:var(--panel,#111923)}
    .unified-subnav a{display:inline-flex;align-items:center;padding:7px 11px;border-radius:8px;text-decoration:none;color:var(--muted,#9aa7b6);font-size:13px;font-weight:600}
    .unified-subnav a:hover{background:rgba(255,255,255,.05);color:var(--text,#edf3f8)}
    .unified-subnav a.active{background:rgba(71,139,255,.15);color:#9fc0ff}
    .architecture-note{margin-bottom:14px}
  `;
  document.head.appendChild(style);
}

function setText(node, text) {
  if (node && node.textContent !== text) node.textContent = text;
}

function replacePanelCopy(heading, subtitle, noticeText = null) {
  for (const article of root.querySelectorAll('article.panel')) {
    const title = article.querySelector('h2');
    if (!title || title.textContent.trim() !== heading) continue;
    if (subtitle) {
      const subtitleNode = title.parentElement?.querySelector('p');
      setText(subtitleNode, subtitle);
    }
    if (noticeText) {
      const notice = article.querySelector('.notice');
      if (notice) {
        notice.classList.remove('warning');
        setText(notice, noticeText);
      }
    }
  }
}

function setParentNavigation(route) {
  const group = ROUTE_GROUPS[route];
  if (!group) return;
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  const parent = document.querySelector(`.nav-item[data-route-group="${group}"]`);
  if (parent) parent.classList.add('active');
}

function addGroupTabs(route) {
  const group = ROUTE_GROUPS[route];
  const tabs = GROUP_TABS[group];
  if (!tabs || !root) return;

  const html = tabs.map(([target, label]) =>
    `<a href="#${target}" class="${target === route || (route === 'host' && target === 'hosts') ? 'active' : ''}">${esc(label)}</a>`
  ).join('');

  let nav = root.querySelector('.unified-subnav');
  if (!nav) {
    nav = document.createElement('nav');
    nav.className = 'unified-subnav';
    root.prepend(nav);
  }
  nav.setAttribute('aria-label', `${group} views`);
  if (nav.dataset.group !== group || nav.innerHTML !== html) {
    nav.dataset.group = group;
    nav.innerHTML = html;
  }
}

function renamePage(route) {
  const title = $('#page-title');
  const subtitle = $('#page-subtitle');
  const titles = {
    overview: ['Dashboard', 'Infrastructure health at a glance'],
    hosts: ['Assets', 'All discovered, manually added and monitored infrastructure'],
    services: ['Asset Services', 'Service state across monitored assets'],
    topology: ['Asset Topology', 'Known relationships between infrastructure assets'],
    discovery: ['Discover Assets', 'Find assets on authorized private networks without changing health state'],
    agentless: ['Monitoring', 'Configure remote WinRM, SSH and SNMP monitoring methods'],
    agents: ['Managed Agent', 'Optional outbound Sentinel Agent enrollment and lifecycle'],
    credentials: ['Monitoring Credentials', 'Encrypted credentials for WinRM, SSH and SNMP'],
    policies: ['Agent Settings', 'Collection and check-in policy for managed agents'],
    rules: ['Alerts', 'Monitoring thresholds that create service states and problems'],
    notifications: ['Alert Notifications', 'Notification channels, automatic delivery and routing status'],
    maintenance: ['Alert Maintenance', 'Scheduled problem suppression and SLA exclusions'],
    events: ['Operational Events', 'Discovery, monitoring and state-transition history'],
    users: ['Access', 'Local users and role management'],
    audit: ['Audit', 'Administrative actions and configuration changes'],
  };
  if (!titles[route] || route === 'host') return;
  setText(title, titles[route][0]);
  setText(subtitle, titles[route][1]);
}

function enhanceAssets(route) {
  if (route === 'hosts') {
    replacePanelCopy('Hosts', 'One asset inventory with monitoring health, services and problems');
    for (const row of root.querySelectorAll('tbody tr')) {
      const cells = row.querySelectorAll('td');
      if (cells.length < 7) continue;
      const stateText = cells[0].textContent.trim().toLowerCase();
      const problems = Number.parseInt(cells[6].textContent.trim(), 10);
      if (stateText.includes('up') && Number.isFinite(problems) && problems > 0) {
        const badgeNode = cells[0].querySelector('.badge');
        if (badgeNode) {
          badgeNode.className = 'badge degraded';
          setText(badgeNode, 'degraded');
        }
      }
    }
  } else if (route === 'discovery') {
    replacePanelCopy(
      'Network discovery',
      'Find and enrich asset identity on authorized private networks',
      'Discovery updates inventory metadata only. Runtime health is determined by configured Monitoring methods; a discovery miss does not mark an asset down.'
    );
  }
}

function enhanceMonitoring(route) {
  if (route !== 'agentless') return;
  replacePanelCopy('Agentless monitoring', 'Configure remote monitoring methods for assets');
  replacePanelCopy(
    'Mode',
    'Choose a monitoring method',
    'Use WinRM for Windows, SSH for Linux/Unix, and SNMP for network, power and appliance monitoring. Managed Sentinel Agent is optional for richer or higher-frequency telemetry.'
  );
  replacePanelCopy('Agentless monitors', 'Remote monitoring assignments');

  if (!root.querySelector('.architecture-note')) {
    const note = document.createElement('div');
    note.className = 'notice architecture-note';
    note.innerHTML = '<strong>Unified workflow:</strong> Discovery answers “what assets exist?”. Monitoring answers “how should SentinelView collect health and performance from each asset?”.';
    const subnav = root.querySelector('.unified-subnav');
    if (subnav) subnav.insertAdjacentElement('afterend', note);
    else root.prepend(note);
  }
}

function deliverySignature(deliveries) {
  return JSON.stringify(deliveries.map(delivery => [
    delivery.id,
    delivery.status,
    delivery.attempts,
    delivery.last_error,
    delivery.created_at,
  ]));
}

async function enhanceNotifications() {
  replacePanelCopy('Add notification channel', 'Webhook, Slack, Teams, Telegram or SMTP delivery');
  replacePanelCopy(
    'Routing',
    'Notification delivery engine',
    'Problem open, escalation, recovery and post-maintenance transitions are queued automatically. Failed deliveries use bounded retry; active maintenance can suppress delivery.'
  );

  let deliveries = [];
  try {
    deliveries = await api('/api/v1/notification-deliveries?limit=50');
  } catch (error) {
    console.warn('Notification delivery history unavailable', error);
  }

  root.querySelectorAll('[data-delete-channel]').forEach(deleteButton => {
    const id = deleteButton.dataset.deleteChannel;
    const cell = deleteButton.closest('td');
    if (!cell || cell.querySelector(`[data-test-channel="${CSS.escape(id)}"]`)) return;
    const button = document.createElement('button');
    button.className = 'link-button';
    button.type = 'button';
    button.dataset.testChannel = id;
    button.textContent = 'Test';
    button.style.marginRight = '8px';
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await api(`/api/v1/notification-channels/${encodeURIComponent(id)}/test`, { method: 'POST' });
        toast(`Test delivery: ${result.status}`);
        scheduleEnhancement();
      } catch (error) {
        toast(error.message, true);
      } finally {
        button.disabled = false;
      }
    };
    cell.insertBefore(button, deleteButton);
  });

  const signature = deliverySignature(deliveries);
  let panel = root.querySelector('#notification-delivery-panel');
  if (!panel) {
    panel = document.createElement('article');
    panel.className = 'panel';
    panel.id = 'notification-delivery-panel';
    root.appendChild(panel);
  }
  if (panel.dataset.signature === signature) return;

  const rows = deliveries.map(delivery => `
    <tr>
      <td>${badge(delivery.status)}</td>
      <td>${esc(delivery.transition)}</td>
      <td>${esc(delivery.severity)}</td>
      <td class="mono">${esc(delivery.channel_id || '—')}</td>
      <td>${Number(delivery.attempts || 0)}</td>
      <td class="delivery-error">${esc(delivery.last_error || '—')}</td>
      <td>${fmtDate(delivery.created_at)}</td>
    </tr>`).join('') || `<tr><td colspan="7">${empty('No notification deliveries yet.')}</td></tr>`;
  panel.dataset.signature = signature;
  panel.innerHTML = `<div class="panel-head"><div><h2>Recent deliveries</h2><p>Last 50 queued, sent, suppressed or failed notifications</p></div><button class="button ghost small" id="refresh-deliveries" type="button">Refresh</button></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>Transition</th><th>Severity</th><th>Channel ID</th><th>Attempts</th><th>Last error</th><th>Created</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  panel.querySelector('#refresh-deliveries')?.addEventListener('click', () => {
    panel.dataset.signature = '';
    scheduleEnhancement();
  });
}

function enhanceMaintenance() {
  replacePanelCopy('Schedule maintenance', 'Suppress matching problem notifications and optionally exclude the window from SLA accounting');
  replacePanelCopy(
    'Behavior',
    'Active maintenance engine',
    'Active host, site or global maintenance windows suppress matching problem notifications when requested. Windows marked for SLA exclusion are removed from the eligible availability denominator.'
  );
  for (const label of root.querySelectorAll('label.checkbox-row')) {
    const text = label.textContent.trim();
    if (text.includes('Suppress notifications metadata')) {
      const input = label.querySelector('input');
      label.textContent = '';
      if (input) label.appendChild(input);
      label.append('Suppress problem notifications');
    } else if (text.includes('Exclude from SLA metadata')) {
      const input = label.querySelector('input');
      label.textContent = '';
      if (input) label.appendChild(input);
      label.append('Exclude from SLA accounting');
    }
  }
}

function enhanceAvailability() {
  for (const cell of root.querySelectorAll('td')) {
    if (cell.textContent.trim() === 'null%' || cell.textContent.trim() === 'undefined%') {
      setText(cell, '—');
    }
  }
}

async function enhanceSettings() {
  if (root.querySelector('#capability-catalog-panel')) return;
  let capabilities = [];
  try {
    capabilities = await api('/api/v1/integrations');
  } catch (error) {
    console.warn('Capability catalog unavailable', error);
    return;
  }
  const panel = document.createElement('article');
  panel.className = 'panel';
  panel.id = 'capability-catalog-panel';
  panel.innerHTML = `<div class="panel-head"><div><h2>Capabilities</h2><p>Collector and platform capabilities; planned packs are not separate product features.</p></div></div><div class="panel-body"><div class="integration-features">${capabilities.map(item => `<span class="badge ${item.status === 'available' ? 'up' : 'unknown'}">${esc(item.name)} · ${esc(item.status)}</span>`).join('')}</div></div>`;
  root.appendChild(panel);
}

async function applyEnhancements() {
  if (running || !root) return;
  running = true;
  try {
    ensureStyles();
    const route = routeName();
    const redirect = LEGACY_REDIRECTS[route];
    if (redirect) {
      location.hash = `#${redirect}`;
      return;
    }

    setParentNavigation(route);
    renamePage(route);
    addGroupTabs(route);

    if (ROUTE_GROUPS[route] === 'assets') enhanceAssets(route);
    if (ROUTE_GROUPS[route] === 'monitoring') enhanceMonitoring(route);
    if (route === 'notifications') await enhanceNotifications();
    else if (route === 'maintenance') enhanceMaintenance();
    else if (route === 'availability') enhanceAvailability();
    else if (route === 'settings') await enhanceSettings();
  } finally {
    running = false;
  }
}

function scheduleEnhancement() {
  if (scheduled) return;
  scheduled = true;
  setTimeout(async () => {
    scheduled = false;
    await applyEnhancements();
  }, 50);
}

if (root) {
  new MutationObserver(() => scheduleEnhancement()).observe(root, { childList: true, subtree: true });
}
window.addEventListener('hashchange', scheduleEnhancement);
window.addEventListener('load', scheduleEnhancement);
scheduleEnhancement();
