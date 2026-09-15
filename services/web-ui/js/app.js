import { api, clearSession, getStoredUser, getToken, login, qs, setSession } from './api.js';
import { $, $$, ago, badge, bytes, closeModal, duration, empty, esc, fmtDate, lineChart, metricValue, openModal, state, statCard, toast, topologyHtml } from './ui.js';

const appState = {
  user: getStoredUser(),
  route: 'overview',
  routeArg: null,
  scanPoll: null,
  searchTimer: null,
  currentScan: null,
};

const ROUTES = {
  overview: ['Overview', 'Infrastructure health at a glance'],
  hosts: ['Hosts', 'Monitored hosts and current state'],
  host: ['Host', 'Host monitoring detail'],
  services: ['Services', 'Service-centric monitoring across all hosts'],
  problems: ['Problems', 'Active warnings, critical conditions and acknowledgements'],
  events: ['Events', 'Operational events and state changes'],
  topology: ['Topology', 'Infrastructure relationships and dependencies'],
  discovery: ['Discovery', 'Find devices on authorized private networks'],
  devices: ['Inventory', 'Discovered and managed infrastructure assets'],
  agents: ['Agents', 'Enroll and manage outbound telemetry agents'],
  policies: ['Agent Policies', 'Central collection policy management'],
  rules: ['Monitoring Rules', 'Thresholds used by services and problems'],
  snmp: ['SNMP', 'Configure network and infrastructure devices'],
  integrations: ['Integrations', 'Monitoring capabilities and integration packs'],
  notifications: ['Notifications', 'Notification channels and routing foundation'],
  maintenance: ['Maintenance', 'Scheduled maintenance and alert suppression metadata'],
  availability: ['Availability & SLA', 'Availability history and service-level targets'],
  users: ['Users & Roles', 'Local access and role management'],
  audit: ['Audit Log', 'Administrative activity and platform changes'],
  settings: ['Settings', 'Platform configuration and component endpoints'],
};

const content = $('#page-content');

function parseRoute() {
  const hash = (location.hash || '#overview').slice(1);
  const [name, arg] = hash.split('/');
  return { name: ROUTES[name] ? name : 'overview', arg: arg || null };
}

function setShellUser() {
  const user = appState.user || { username: 'unknown', role: 'viewer' };
  $('#user-name').textContent = user.username || 'unknown';
  $('#user-role').textContent = user.role || 'viewer';
  $('#user-avatar').textContent = (user.username || 'U').slice(0, 1).toUpperCase();
  $$('.admin-only').forEach(el => el.classList.toggle('hidden', user.role !== 'admin'));
  $('#quick-add-btn').classList.toggle('hidden', user.role === 'viewer');
}

function showLogin() {
  $('#app-shell').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
  setTimeout(() => $('#login-password')?.focus(), 50);
}

function showApp() {
  $('#login-screen').classList.add('hidden');
  $('#app-shell').classList.remove('hidden');
  setShellUser();
}

async function authenticateExistingSession() {
  if (!getToken()) { showLogin(); return false; }
  try {
    const identity = await api('/api/v1/auth/me');
    appState.user = { username: identity.username, role: identity.role };
    localStorage.setItem('sentinelview.user', JSON.stringify(appState.user));
    showApp();
    return true;
  } catch {
    showLogin();
    return false;
  }
}

async function handleLogin(event) {
  event.preventDefault();
  $('#login-error').textContent = '';
  const button = event.currentTarget.querySelector('button[type="submit"]');
  button.disabled = true; button.textContent = 'Signing in...';
  try {
    const result = await login($('#login-username').value.trim(), $('#login-password').value);
    setSession(result.token, result.user);
    appState.user = result.user;
    showApp();
    await navigateFromHash();
  } catch (error) {
    $('#login-error').textContent = error.message;
  } finally {
    button.disabled = false; button.textContent = 'Sign in';
  }
}

async function checkApiHealth() {
  try {
    const response = await fetch('/control-health');
    if (!response.ok) throw new Error('down');
    $('#api-dot').className = 'status-dot up';
    $('#api-label').textContent = 'Control API online';
  } catch {
    $('#api-dot').className = 'status-dot down';
    $('#api-label').textContent = 'Control API unavailable';
  }
}

function setPageChrome(route, arg = null) {
  const meta = ROUTES[route] || ROUTES.overview;
  $('#page-title').textContent = meta[0];
  $('#page-subtitle').textContent = meta[1];
  $$('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.route === route || (route === 'host' && item.dataset.route === 'hosts')));
  const crumbs = route === 'host'
    ? `<a href="#hosts">Hosts</a><span>/</span><span>${esc(arg || 'Host')}</span>`
    : `<span>SentinelView</span><span>/</span><span>${esc(meta[0])}</span>`;
  $('#breadcrumb').innerHTML = crumbs;
}

function loading() {
  content.innerHTML = `<div class="panel"><div class="empty">Loading SentinelView data...</div></div>`;
}

function errorPanel(error) {
  content.innerHTML = `<div class="panel"><div class="panel-body"><div class="notice danger"><strong>Could not load this page.</strong><br>${esc(error.message || error)}</div></div></div>`;
}

function hostNameById(hosts, id) {
  return hosts.find(h => h.id === id)?.hostname || hosts.find(h => h.id === id)?.ip_address || id;
}

async function renderOverview() {
  const data = await api('/api/v1/ui/overview');
  const p = data.problems, h = data.hosts, s = data.services, a = data.agents;
  $('#nav-problem-count').textContent = p.total;
  $('#nav-problem-count').classList.toggle('hidden', !p.total);
  const problemRows = (data.recent_problems || []).map(problem => `
    <div class="list-item row-click" data-action="open-problem" data-problem-id="${esc(problem.id)}" data-host-id="${esc(problem.device_id)}">
      <div class="severity-bar ${esc(problem.severity)}"></div>
      <div><div class="list-title">${esc(problem.title)}</div><div class="list-sub">${esc(problem.message)} · ${ago(problem.opened_at)}</div></div>
      ${badge(problem.state === 'acknowledged' ? 'acknowledged' : problem.severity)}
    </div>`).join('') || empty('No active problems.');
  const siteRows = (data.sites || []).map(site => `<tr><td><strong>${esc(site.site)}</strong></td><td>${site.total}</td><td>${site.up}</td><td>${site.down}</td><td>${site.problems}</td></tr>`).join('') || `<tr><td colspan="5">${empty('No sites yet.')}</td></tr>`;
  const eventRows = (data.recent_events || []).map(event => `<div class="list-item"><div class="severity-bar ${esc(event.severity)}"></div><div><div class="list-title">${esc(event.message)}</div><div class="list-sub">${esc(event.event_type)} · ${ago(event.created_at)}</div></div>${badge(event.severity)}</div>`).join('') || empty('No events yet.');
  content.innerHTML = `
    <div class="page-stack">
      <div class="stat-grid">
        ${statCard('Hosts', h.total, `${h.up} up · ${h.down} down`, h.down ? 'red' : 'green')}
        ${statCard('Services', s.total, `${s.ok} OK · ${s.warning} warning · ${s.critical} critical`, s.critical ? 'red' : s.warning ? 'yellow' : 'green')}
        ${statCard('Problems', p.total, `${p.critical} critical · ${p.warning} warning`, p.critical ? 'red' : p.warning ? 'yellow' : 'green')}
        ${statCard('Agents', `${a.online}/${a.total}`, `${a.offline} offline`, a.offline ? 'yellow' : 'blue')}
      </div>
      <div class="grid-main-aside">
        <article class="panel"><div class="panel-head"><div><h2>Active problems</h2><p>Conditions that currently need attention</p></div><a class="link-button" href="#problems">View all →</a></div><div class="problem-list">${problemRows}</div></article>
        <article class="panel"><div class="panel-head"><div><h2>Sites</h2><p>Health by location</p></div></div><div class="table-wrap"><table><thead><tr><th>Site</th><th>Hosts</th><th>Up</th><th>Down</th><th>Problems</th></tr></thead><tbody>${siteRows}</tbody></table></div></article>
      </div>
      <div class="grid-2">
        <article class="panel"><div class="panel-head"><div><h2>Service health</h2><p>Derived from host telemetry and monitoring rules</p></div></div><div class="panel-body"><div class="stat-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">${statCard('OK', s.ok, '', 'green')}${statCard('Warning', s.warning, '', 'yellow')}${statCard('Critical', s.critical, '', 'red')}${statCard('Unknown', s.unknown, '', '')}</div></div></article>
        <article class="panel"><div class="panel-head"><div><h2>Recent events</h2><p>Discovery, enrollment and state changes</p></div><a class="link-button" href="#events">Event log →</a></div><div class="event-list">${eventRows}</div></article>
      </div>
    </div>`;
}

async function renderHosts() {
  const hosts = await api('/api/v1/hosts');
  content.innerHTML = `
    <div class="page-stack">
      <article class="panel">
        <div class="panel-head"><div><h2>Hosts</h2><p>${hosts.length} monitored assets</p></div><div class="panel-actions"><input id="hosts-search" placeholder="Search hostname or IP"/><select id="hosts-state"><option value="">All states</option><option value="up">Up</option><option value="down">Down</option><option value="unknown">Unknown</option></select><select id="hosts-site"><option value="">All sites</option>${[...new Set(hosts.map(h=>h.site||'default'))].sort().map(site=>`<option value="${esc(site)}">${esc(site)}</option>`).join('')}</select><button class="button primary small" data-nav="discovery">Discover</button></div></div>
        <div class="table-wrap"><table><thead><tr><th>State</th><th>Host</th><th>Site</th><th>OS / Type</th><th>Agent</th><th>Services</th><th>Problems</th><th>Last seen</th></tr></thead><tbody id="hosts-body"></tbody></table></div>
      </article>
    </div>`;
  const draw = () => {
    const query = ($('#hosts-search').value || '').toLowerCase();
    const filter = $('#hosts-state').value; const site = $('#hosts-site').value;
    const rows = hosts.filter(h => (!filter || h.state === filter) && (!site || (h.site || 'default') === site) && (!query || `${h.hostname || ''} ${h.ip_address}`.toLowerCase().includes(query)));
    $('#hosts-body').innerHTML = rows.map(h => `<tr class="row-click" data-host-id="${esc(h.id)}"><td>${state(h.state)}</td><td><div class="primary-cell"><strong>${esc(h.hostname || 'Unknown')}</strong><span>${esc(h.ip_address)}</span></div></td><td>${esc(h.site || 'default')}</td><td>${esc(h.os_name || h.device_class || 'unknown')}</td><td>${h.agent_enabled ? badge(h.agent_online ? 'online' : 'offline', h.agent_version || (h.agent_online ? 'online' : 'offline')) : badge('unknown','none')}</td><td>${h.service_count}</td><td>${h.problem_count ? `<span class="badge ${h.critical_count ? 'critical' : 'warning'}">${h.problem_count}</span>` : badge('ok','0')}</td><td>${ago(h.last_seen)}</td></tr>`).join('') || `<tr><td colspan="8">${empty('No hosts match the current filters.')}</td></tr>`;
  };
  draw();
  $('#hosts-search').addEventListener('input', draw); $('#hosts-state').addEventListener('change', draw); $('#hosts-site').addEventListener('change', draw);
}

async function renderHost(id) {
  const data = await api(`/api/v1/hosts/${encodeURIComponent(id)}/overview`);
  const d = data.device, t = data.telemetry, agent = data.agent;
  $('#page-title').textContent = d.hostname || d.ip_address;
  $('#page-subtitle').textContent = `${d.ip_address} · ${d.os_name || d.device_class}`;
  $('#breadcrumb').innerHTML = `<a href="#hosts">Hosts</a><span>/</span><span>${esc(d.hostname || d.ip_address)}</span>`;
  const [cpuHistory, memoryHistory] = await Promise.all([
    api(`/api/v1/hosts/${encodeURIComponent(id)}/metrics?metric=cpu&range=1h`).catch(() => ({series:[]})),
    api(`/api/v1/hosts/${encodeURIComponent(id)}/metrics?metric=memory&range=1h`).catch(() => ({series:[]})),
  ]);
  const disks = (t?.disks || []).map(disk => `<div class="metric-card"><h3>Disk ${esc(disk.mountpoint)}</h3><div class="metric-value">${metricValue(disk.usage_percent,'%')}</div><div class="metric-sub">${bytes(disk.used_bytes)} / ${bytes(disk.total_bytes)} · ${esc(disk.fstype || '')}</div><div class="progress" style="margin-top:9px"><span style="width:${Math.min(100, Number(disk.usage_percent || 0))}%"></span></div></div>`).join('') || `<div class="metric-card"><h3>Disk</h3><div class="metric-sub">No disk telemetry</div></div>`;
  const serviceRows = (data.services || []).map(s => `<tr><td>${badge(s.state)}</td><td><strong>${esc(s.service_name)}</strong></td><td>${esc(s.value ?? '—')}${s.unit ? esc(s.unit) : ''}</td><td>${esc(s.message)}</td><td>${ago(s.updated_at)}</td></tr>`).join('');
  const problemRows = (data.problems || []).map(p => `<div class="list-item"><div class="severity-bar ${esc(p.severity)}"></div><div><div class="list-title">${esc(p.title)}</div><div class="list-sub">${esc(p.message)} · ${ago(p.opened_at)}</div></div>${badge(p.state === 'acknowledged' ? 'acknowledged' : p.severity)}</div>`).join('') || empty('No active problems on this host.');
  content.innerHTML = `
    <div class="page-stack">
      <article class="panel">
        <div class="host-hero"><div class="host-title"><div class="device-icon">${esc((d.device_class || 'H').slice(0,2).toUpperCase())}</div><div><h2>${esc(d.hostname || d.ip_address)}</h2><p>${esc(d.ip_address)} · ${esc(d.os_name || 'Unknown OS')} · ${esc(d.device_class)}</p><div class="tags">${(d.tags || []).map(tag => `<span class="tag">${esc(tag)}</span>`).join('')}<span class="tag">${esc(d.site || 'default')}</span></div></div></div><div>${badge(d.state)} ${agent ? badge(agent.online ? 'online' : 'offline', `agent ${agent.version}`) : ''}</div></div>
      </article>
      <div class="stat-grid">
        ${statCard('CPU', metricValue(t?.cpu_usage_percent,'%'), 'Latest agent telemetry', t?.cpu_usage_percent >= 95 ? 'red' : t?.cpu_usage_percent >= 80 ? 'yellow' : 'green')}
        ${statCard('Memory', metricValue(t?.memory_usage_percent,'%'), t ? `${bytes(t.memory_used_bytes)} / ${bytes(t.memory_total_bytes)}` : 'No telemetry', t?.memory_usage_percent >= 95 ? 'red' : t?.memory_usage_percent >= 85 ? 'yellow' : 'green')}
        ${statCard('Processes', t?.process_count ?? '—', 'Running processes', 'blue')}
        ${statCard('Uptime', duration(t?.uptime_seconds), agent ? `Last check-in ${ago(agent.last_checkin)}` : 'No managed agent', 'blue')}
      </div>
      <div class="grid-2">
        <article class="panel"><div class="panel-head"><div><h2>CPU utilization</h2><p>Prometheus history · last hour</p></div><a class="link-button" href="http://${location.hostname}:3000" target="_blank">Advanced ↗</a></div><div class="panel-body chart">${lineChart(cpuHistory.series,{unit:'%',max:100})}</div></article>
        <article class="panel"><div class="panel-head"><div><h2>Memory utilization</h2><p>Prometheus history · last hour</p></div></div><div class="panel-body chart">${lineChart(memoryHistory.series,{unit:'%',max:100})}</div></article>
      </div>
      <article class="panel"><div class="panel-head"><div><h2>Storage</h2><p>Latest disk telemetry</p></div></div><div class="panel-body"><div class="grid-3">${disks}</div></div></article>
      <article class="panel"><div class="panel-head"><div><h2>Network interfaces</h2><p>Latest cumulative interface counters</p></div></div><div class="table-wrap"><table><thead><tr><th>Interface</th><th>Received</th><th>Transmitted</th><th>Collection</th></tr></thead><tbody>${(t?.interfaces||[]).map(n=>`<tr><td><strong>${esc(n.name)}</strong></td><td>${bytes(n.receive_bytes_total)}</td><td>${bytes(n.transmit_bytes_total)}</td><td>${badge('up','collecting')}</td></tr>`).join('')||`<tr><td colspan="4">${empty('No network interface telemetry.')}</td></tr>`}</tbody></table></div></article>
      <div class="grid-main-aside">
        <article class="panel"><div class="panel-head"><div><h2>Services</h2><p>Current service-centric monitoring state</p></div><a class="link-button" href="#services">All services →</a></div><div class="table-wrap"><table><thead><tr><th>State</th><th>Service</th><th>Value</th><th>Output</th><th>Updated</th></tr></thead><tbody>${serviceRows}</tbody></table></div></article>
        <article class="panel"><div class="panel-head"><div><h2>Problems</h2><p>Active conditions</p></div></div><div>${problemRows}</div></article>
      </div>
      <article class="panel"><div class="panel-head"><div><h2>Inventory</h2><p>Control-plane host metadata</p></div></div><div class="panel-body"><div class="kv-grid">${kv('Hostname',d.hostname||'—')}${kv('IP address',d.ip_address)}${kv('MAC',d.mac_address||'—')}${kv('Vendor',d.vendor||'—')}${kv('Model',d.model||'—')}${kv('OS',d.os_name||'—')}${kv('Class',d.device_class)}${kv('Site',d.site||'default')}${kv('Open ports',(d.open_ports||[]).join(', ')||'—')}${kv('First seen',fmtDate(d.first_seen))}${kv('Last seen',fmtDate(d.last_seen))}${kv('Agent ID',agent?.id||'—')}</div></div></article>
    </div>`;
}

function kv(label, value) { return `<div class="kv"><label>${esc(label)}</label><div>${esc(value)}</div></div>`; }

async function renderServices() {
  const services = await api('/api/v1/services');
  content.innerHTML = `<article class="panel"><div class="panel-head"><div><h2>Services</h2><p>${services.length} checks derived from current telemetry and inventory</p></div><div class="filters"><input id="service-search" placeholder="Search host or service"/><select id="service-state"><option value="">All states</option><option value="ok">OK</option><option value="warning">Warning</option><option value="critical">Critical</option><option value="unknown">Unknown</option></select></div></div><div class="table-wrap"><table><thead><tr><th>State</th><th>Host</th><th>Service</th><th>Value</th><th>Output</th><th>Updated</th></tr></thead><tbody id="services-body"></tbody></table></div></article>`;
  const draw = () => {
    const q = ($('#service-search').value || '').toLowerCase(), st = $('#service-state').value;
    const rows = services.filter(s => (!st || s.state === st) && (!q || `${s.hostname} ${s.service_name} ${s.message}`.toLowerCase().includes(q)));
    $('#services-body').innerHTML = rows.map(s => `<tr class="row-click" data-host-id="${esc(s.host_id)}"><td>${badge(s.state)}</td><td>${esc(s.hostname)}</td><td><strong>${esc(s.service_name)}</strong></td><td>${esc(s.value ?? '—')}${s.unit ? esc(s.unit) : ''}</td><td>${esc(s.message)}</td><td>${ago(s.updated_at)}</td></tr>`).join('') || `<tr><td colspan="6">${empty('No services match the current filters.')}</td></tr>`;
  };
  draw(); $('#service-search').addEventListener('input',draw); $('#service-state').addEventListener('change',draw);
}

async function renderProblems() {
  const [problems, hosts] = await Promise.all([api('/api/v1/problems?state=active'), api('/api/v1/hosts')]);
  const hostname = id => hostNameById(hosts,id);
  content.innerHTML = `<article class="panel"><div class="panel-head"><div><h2>Active problems</h2><p>${problems.length} active conditions</p></div><div class="filters"><select id="problem-severity"><option value="">All severities</option><option value="critical">Critical</option><option value="warning">Warning</option></select><input id="problem-search" placeholder="Search host / service"/></div></div><div class="table-wrap"><table><thead><tr><th>Severity</th><th>Since</th><th>Host</th><th>Service</th><th>Message</th><th>State</th><th></th></tr></thead><tbody id="problems-body"></tbody></table></div></article>`;
  const draw = () => {
    const q = ($('#problem-search').value || '').toLowerCase(), sev = $('#problem-severity').value;
    const rows = problems.filter(p => (!sev || p.severity === sev) && (!q || `${hostname(p.device_id)} ${p.service_name} ${p.message}`.toLowerCase().includes(q)));
    $('#problems-body').innerHTML = rows.map(p => `<tr><td>${badge(p.severity)}</td><td>${ago(p.opened_at)}</td><td><a class="link-button" href="#host/${esc(p.device_id)}">${esc(hostname(p.device_id))}</a></td><td>${esc(p.service_name)}</td><td>${esc(p.message)}</td><td>${badge(p.state)}</td><td>${p.state === 'open' ? `<button class="button ghost small" data-ack-problem="${esc(p.id)}">Acknowledge</button>` : '—'}</td></tr>`).join('') || `<tr><td colspan="7">${empty('No active problems. Infrastructure is healthy.')}</td></tr>`;
    $$('[data-ack-problem]').forEach(btn => btn.onclick = async () => { try { await api(`/api/v1/problems/${btn.dataset.ackProblem}/ack`,{method:'POST'}); toast('Problem acknowledged'); await renderProblems(); } catch(e){toast(e.message,true);} });
  };
  draw(); $('#problem-search').addEventListener('input',draw); $('#problem-severity').addEventListener('change',draw);
}

async function renderEvents() {
  const events = await api('/api/v1/events?limit=300');
  content.innerHTML = `<article class="panel"><div class="panel-head"><div><h2>Event log</h2><p>Discovery, agent lifecycle and state-change events</p></div><input id="event-search" placeholder="Search events"/></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>Severity</th><th>Type</th><th>Message</th><th>Device</th></tr></thead><tbody id="events-body"></tbody></table></div></article>`;
  const draw = () => { const q=($('#event-search').value||'').toLowerCase(); const rows=events.filter(e=>!q||`${e.message} ${e.event_type}`.toLowerCase().includes(q)); $('#events-body').innerHTML=rows.map(e=>`<tr><td>${fmtDate(e.created_at)}</td><td>${badge(e.severity)}</td><td class="mono">${esc(e.event_type)}</td><td>${esc(e.message)}</td><td>${e.device_id?`<a class="link-button" href="#host/${esc(e.device_id)}">Open host</a>`:'—'}</td></tr>`).join('')||`<tr><td colspan="5">${empty('No events.')}</td></tr>`; };
  draw(); $('#event-search').addEventListener('input',draw);
}

function hostCount(cidr) {
  try { const [ip,prefixText]=cidr.split('/'); const prefix=Number(prefixText); if(!ip||prefix<0||prefix>32)return null; const total=2**(32-prefix); return prefix<=30?Math.max(0,total-2):total; } catch { return null; }
}
function scanPercent(scan) { const total=hostCount(scan.cidr); return total ? Math.min(100,Math.round((scan.scanned/total)*100)) : scan.status==='complete'?100:0; }

async function renderDiscovery() {
  const scans = await api('/api/v1/discovery/scans?limit=100');
  const active = scans.find(s => ['pending','claimed','running'].includes(s.status));
  content.innerHTML = `
    <div class="page-stack">
      <div class="grid-main-aside">
        <article class="panel"><div class="panel-head"><div><h2>Network discovery</h2><p>Scan private networks you own or are authorized to manage</p></div></div><div class="panel-body"><form id="scan-form" class="form-stack"><div class="form-grid"><label>Network / CIDR<input id="scan-cidr" value="192.168.1.0/24" required /></label><label>Site<input id="scan-site" value="default" /></label></div><div class="notice">SentinelView rejects public address ranges. Discovery currently uses ICMP and TCP fallback probes; SNMP profiles are configured separately.</div><div><button class="button primary" type="submit">Start discovery</button></div></form></div></article>
        <article class="panel"><div class="panel-head"><div><h2>Quick networks</h2><p>Common private ranges</p></div></div><div class="panel-body"><div class="form-stack">${['192.168.1.0/24','192.168.0.0/24','10.0.0.0/24','172.16.0.0/24'].map(c=>`<button class="button ghost" data-cidr="${c}">${c}</button>`).join('')}</div></div></article>
      </div>
      ${active ? `<article class="panel"><div class="panel-head"><div><h2>Active scan</h2><p>${esc(active.cidr)} · ${esc(active.site||'default')}</p></div>${badge(active.status)}</div><div class="panel-body"><div class="progress"><span style="width:${scanPercent(active)}%"></span></div><div class="metric-sub" style="margin-top:8px">${active.scanned} scanned · ${active.discovered} discovered · ${scanPercent(active)}%</div></div></article>` : ''}
      <article class="panel"><div class="panel-head"><div><h2>Scan history</h2><p>Discovery job status and results</p></div></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>CIDR</th><th>Site</th><th>Progress</th><th>Discovered</th><th>Started</th><th>Finished</th></tr></thead><tbody>${scans.map(s=>`<tr><td>${badge(s.status)}</td><td class="mono">${esc(s.cidr)}</td><td>${esc(s.site||'default')}</td><td><div style="min-width:130px"><div class="progress"><span style="width:${scanPercent(s)}%"></span></div><div class="metric-sub">${s.scanned} · ${scanPercent(s)}%</div></div></td><td>${s.discovered}</td><td>${fmtDate(s.started_at||s.created_at)}</td><td>${fmtDate(s.finished_at)}</td></tr>`).join('')}</tbody></table></div></article>
    </div>`;
  $$('[data-cidr]').forEach(btn=>btn.onclick=()=>{$('#scan-cidr').value=btn.dataset.cidr;});
  $('#scan-form').onsubmit = async event => { event.preventDefault(); const button=event.currentTarget.querySelector('button[type="submit"]'); button.disabled=true; try { const scan=await api('/api/v1/discovery/scans',{method:'POST',body:JSON.stringify({cidr:$('#scan-cidr').value.trim(),site:$('#scan-site').value.trim()||null})}); toast(`Discovery started for ${scan.cidr}`); appState.currentScan=scan.id; startScanPolling(); await renderDiscovery(); } catch(e){toast(e.message,true);} finally{button.disabled=false;} };
  if (active && !appState.scanPoll) { appState.currentScan=active.id; startScanPolling(); }
}

function startScanPolling() {
  if (appState.scanPoll) clearInterval(appState.scanPoll);
  appState.scanPoll=setInterval(async()=>{
    if(!appState.currentScan)return;
    try { const scan=await api(`/api/v1/discovery/scans/${appState.currentScan}`); if(['complete','failed'].includes(scan.status)){clearInterval(appState.scanPoll);appState.scanPoll=null;appState.currentScan=null;toast(scan.status==='complete'?`Discovery completed: ${scan.discovered} devices`:`Discovery failed: ${scan.error}`,scan.status==='failed');} if(appState.route==='discovery') await renderDiscovery(); } catch(e){console.warn(e);}
  },2500);
}

async function renderDevices() {
  const devices=await api('/api/v1/devices?limit=5000');
  content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Infrastructure inventory</h2><p>${devices.length} assets from discovery, agents and manual configuration</p></div><div class="filters"><input id="device-search" placeholder="Search inventory"/><select id="device-state"><option value="">All states</option><option value="up">Up</option><option value="down">Down</option><option value="unknown">Unknown</option></select></div></div><div class="table-wrap"><table><thead><tr><th>State</th><th>Hostname</th><th>IP / MAC</th><th>Class</th><th>Vendor / Model</th><th>Site</th><th>Agent</th><th>SNMP</th><th>Last seen</th></tr></thead><tbody id="devices-body"></tbody></table></div></article>`;
  const draw=()=>{const q=($('#device-search').value||'').toLowerCase(),st=$('#device-state').value;const rows=devices.filter(d=>(!st||d.state===st)&&(!q||`${d.hostname||''} ${d.ip_address} ${d.mac_address||''} ${d.vendor||''}`.toLowerCase().includes(q)));$('#devices-body').innerHTML=rows.map(d=>`<tr class="row-click" data-host-id="${esc(d.id)}"><td>${state(d.state)}</td><td><strong>${esc(d.hostname||'Unknown')}</strong></td><td><div class="primary-cell"><strong class="mono">${esc(d.ip_address)}</strong><span>${esc(d.mac_address||'—')}</span></div></td><td>${esc(d.device_class)}</td><td>${esc([d.vendor,d.model].filter(Boolean).join(' ')||'—')}</td><td>${esc(d.site||'default')}</td><td>${d.agent_enabled?badge('online',d.agent_version||'enabled'):badge('unknown','none')}</td><td>${d.snmp_enabled?badge('up',d.snmp_module):badge('unknown','off')}</td><td>${ago(d.last_seen)}</td></tr>`).join('')||`<tr><td colspan="9">${empty('No inventory matches the current filters.')}</td></tr>`;};draw();$('#device-search').addEventListener('input',draw);$('#device-state').addEventListener('change',draw);
}

function psQuote(value){return `'${String(value).replace(/'/g,"''")}'`;}
function shQuote(value){return `'${String(value).replace(/'/g,"'\\''")}'`;}
function installCommand(osName, server, token, site, tags) {
  server = server.replace(/\/+$/, '');
  tags = (tags || '').trim();

  if (osName === 'windows') {
    const tagsArg = tags
      ? ` -Tags ${psQuote(tags)}`
      : '';

    return `$p=Join-Path $env:TEMP 'sentinel-install.ps1'; ` +
      `Invoke-WebRequest -UseBasicParsing ${psQuote(server + '/install/windows.ps1')} -OutFile $p; ` +
      `Set-ExecutionPolicy -Scope Process Bypass -Force; ` +
      `& $p ` +
      `-Server ${psQuote(server)} ` +
      `-Token ${psQuote(token)} ` +
      `-Site ${psQuote(site)}` +
      tagsArg;
  }

  const tagsArg = tags
    ? ` --tags ${shQuote(tags)}`
    : '';

  return `curl -fsSL ${shQuote(server + '/install/linux.sh')} | ` +
    `sudo sh -s -- ` +
    `--server ${shQuote(server)} ` +
    `--token ${shQuote(token)} ` +
    `--site ${shQuote(site)}` +
    tagsArg;
}
function defaultControlUrl(){return `http://${location.hostname}:8080`;}

async function renderAgents() {
  const [agents,policies,tokens]=await Promise.all([api('/api/v1/agents'),api('/api/v1/agent-policies'),api('/api/v1/agents/enrollment-tokens').catch(()=>[])]);
  const policyName=id=>policies.find(p=>p.id===id)?.name||id?.slice(0,8)||'—';
  const online=agents.filter(a=>a.online&&!a.revoked).length, offline=agents.filter(a=>!a.online&&!a.revoked).length;
  content.innerHTML=`<div class="page-stack"><div class="stat-grid">${statCard('Managed agents',agents.length,'Enrolled endpoints','blue')}${statCard('Online',online,'Recent check-in','green')}${statCard('Offline',offline,'No recent check-in',offline?'yellow':'green')}${statCard('Policies',policies.length,'Central collection profiles','blue')}</div><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>Add managed agent</h2><p>One-command outbound enrollment</p></div></div><div class="panel-body"><form id="agent-install-form" class="form-stack"><div class="form-grid"><label>Operating system<select id="agent-os"><option value="windows">Windows x64</option><option value="linux">Linux x64</option></select></label><label>Policy<select id="agent-policy">${policies.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label><label>SentinelView server URL<input id="agent-server" value="${esc(defaultControlUrl())}" /></label><label>Site<input id="agent-site" value="default" /></label><label>Tags<input id="agent-tags" placeholder="production,windows" /></label><label>Token lifetime<select id="agent-expiry"><option value="30">30 minutes</option><option value="60">1 hour</option><option value="1440">24 hours</option></select></label></div><div class="notice">Remote endpoints should use the LAN/DNS URL of the SentinelView control plane, not <code>localhost</code>. Managed agents push telemetry outbound and do not require inbound port 9123.</div><button class="button primary" type="submit">Generate install command</button></form></div></article><article class="panel"><div class="panel-head"><div><h2>Installer</h2><p>Generated short-lived enrollment command</p></div></div><div id="installer-output" class="panel-body">${empty('Generate an install command to enroll a Windows or Linux endpoint.')}</div></article></div><article class="panel"><div class="panel-head"><div><h2>Managed agents</h2><p>Endpoint lifecycle and connectivity</p></div></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>Hostname</th><th>IP</th><th>OS</th><th>Version</th><th>Policy</th><th>Site</th><th>Last check-in</th><th></th></tr></thead><tbody>${agents.map(a=>`<tr><td>${badge(a.revoked?'failed':a.online?'online':'offline',a.revoked?'revoked':a.online?'online':'offline')}</td><td><a class="link-button" href="#host/${esc(a.device_id)}">${esc(a.hostname)}</a></td><td class="mono">${esc(a.last_ip||'—')}</td><td>${esc(a.os_name)} / ${esc(a.arch)}</td><td>${esc(a.version)}</td><td>${esc(policyName(a.policy_id))} v${a.policy_version}</td><td>${esc(a.site||'default')}</td><td>${ago(a.last_checkin)}</td><td>${!a.revoked?`<button class="link-button danger" data-revoke-agent="${esc(a.id)}">Revoke</button>`:'—'}</td></tr>`).join('')||`<tr><td colspan="9">${empty('No managed agents enrolled yet.')}</td></tr>`}</tbody></table></div></article><article class="panel"><div class="panel-head"><div><h2>Enrollment tokens</h2><p>Plaintext tokens are only shown at creation</p></div></div><div class="table-wrap"><table><thead><tr><th>Prefix</th><th>Policy</th><th>Site</th><th>Uses</th><th>Expires</th><th>Status</th></tr></thead><tbody>${tokens.map(t=>`<tr><td class="mono">${esc(t.token_prefix)}…</td><td>${esc(policyName(t.policy_id))}</td><td>${esc(t.site||'default')}</td><td>${t.used_count}/${t.max_uses}</td><td>${fmtDate(t.expires_at)}</td><td>${badge(t.revoked?'failed':t.used_count>=t.max_uses?'unknown':'up',t.revoked?'revoked':t.used_count>=t.max_uses?'exhausted':'active')}</td></tr>`).join('')||`<tr><td colspan="6">${empty('No enrollment tokens.')}</td></tr>`}</tbody></table></div></article></div>`;
  $('#agent-install-form').onsubmit=async event=>{event.preventDefault();try{const created=await api('/api/v1/agents/enrollment-tokens',{method:'POST',body:JSON.stringify({policy_id:$('#agent-policy').value,site:$('#agent-site').value.trim()||'default',expires_in_minutes:Number($('#agent-expiry').value),max_uses:1})});const command=installCommand($('#agent-os').value,$('#agent-server').value.trim(),created.token,$('#agent-site').value.trim()||'default',$('#agent-tags').value.trim());$('#installer-output').innerHTML=`<div class="form-stack"><div><div class="stat-label">One-time token</div><div class="command-box">${esc(created.token)}</div></div><div><div class="stat-label">Install command</div><pre class="command-box" id="install-command">${esc(command)}</pre></div><button class="button primary" id="copy-install" type="button">Copy command</button><div class="form-help">Run on the endpoint with Administrator/root privileges. The installer verifies SHA-256, enrolls, installs the OS service and starts it.</div></div>`;$('#copy-install').onclick=()=>navigator.clipboard.writeText(command).then(()=>toast('Install command copied')).catch(()=>toast('Clipboard unavailable',true));toast('Enrollment token created');}catch(e){toast(e.message,true);}};
  $$('[data-revoke-agent]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Revoke this agent credential?'))return;try{await api(`/api/v1/agents/${btn.dataset.revokeAgent}/revoke`,{method:'POST'});toast('Agent revoked');await renderAgents();}catch(e){toast(e.message,true);}});
}

async function renderPolicies() {
  const policies=await api('/api/v1/agent-policies');
  content.innerHTML=`<div class="page-stack"><article class="panel"><div class="panel-head"><div><h2>Agent policies</h2><p>Collection intervals and enabled collectors</p></div><button class="button primary small" id="new-policy">+ New policy</button></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Version</th><th>Telemetry</th><th>Check-in</th><th>Collectors</th><th>Default</th><th></th></tr></thead><tbody>${policies.map(p=>{const c=p.config||{};const collectors=['CPU','Memory','Disk','Network','Processes'].filter((_,i)=>[c.collect_cpu,c.collect_memory,c.collect_disk,c.collect_network,c.collect_process_count][i]).join(', ');return`<tr><td><strong>${esc(p.name)}</strong></td><td>v${p.version}</td><td>${c.telemetry_interval_seconds||15}s</td><td>${c.checkin_interval_seconds||30}s</td><td>${esc(collectors||'none')}</td><td>${p.is_default?badge('up','default'):'—'}</td><td><button class="link-button" data-edit-policy="${esc(p.id)}">Edit</button></td></tr>`;}).join('')}</tbody></table></div></article></div>`;
  $('#new-policy').onclick=()=>policyModal(null);
  $$('[data-edit-policy]').forEach(btn=>btn.onclick=()=>policyModal(policies.find(p=>p.id===btn.dataset.editPolicy)));
}

function policyModal(policy) {
  const c=policy?.config||{telemetry_interval_seconds:15,checkin_interval_seconds:30,collect_cpu:true,collect_memory:true,collect_disk:true,collect_network:true,collect_process_count:true};
  openModal(policy?'Edit agent policy':'Create agent policy',policy?'Changes are pulled by agents on check-in.':'Create a reusable endpoint collection policy.',`<form id="policy-form" class="form-stack"><label>Name<input id="policy-name" value="${esc(policy?.name||'')}" ${policy?'disabled':''} required/></label><div class="form-grid"><label>Telemetry interval (seconds)<input id="policy-telemetry" type="number" min="5" value="${c.telemetry_interval_seconds||15}"/></label><label>Check-in interval (seconds)<input id="policy-checkin" type="number" min="10" value="${c.checkin_interval_seconds||30}"/></label></div>${[['cpu','CPU'],['memory','Memory'],['disk','Disk'],['network','Network'],['process_count','Process count']].map(([key,label])=>`<label class="checkbox-row"><input id="policy-${key}" type="checkbox" ${c[`collect_${key}`]!==false?'checked':''}/>${label}</label>`).join('')}<button class="button primary" type="submit">${policy?'Save policy':'Create policy'}</button></form>`);
  $('#policy-form').onsubmit=async event=>{event.preventDefault();const payload={telemetry_interval_seconds:Number($('#policy-telemetry').value),checkin_interval_seconds:Number($('#policy-checkin').value),collect_cpu:$('#policy-cpu').checked,collect_memory:$('#policy-memory').checked,collect_disk:$('#policy-disk').checked,collect_network:$('#policy-network').checked,collect_process_count:$('#policy-process_count').checked};try{if(policy){await api(`/api/v1/agent-policies/${policy.id}`,{method:'PATCH',body:JSON.stringify(payload)});}else{await api('/api/v1/agent-policies',{method:'POST',body:JSON.stringify({name:$('#policy-name').value.trim(),...payload})});}closeModal();toast(policy?'Policy updated':'Policy created');await renderPolicies();}catch(e){toast(e.message,true);}};
}

async function renderRules() {
  const rules=await api('/api/v1/rules');
  content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Monitoring rules</h2><p>Rules drive service state and active problems</p></div><button class="button primary small" id="new-rule">+ New rule</button></div><div class="table-wrap"><table><thead><tr><th>Rule</th><th>Metric</th><th>Condition</th><th>Warning</th><th>Critical</th><th>For</th><th>Status</th><th></th></tr></thead><tbody>${rules.map(r=>`<tr><td><strong>${esc(r.name)}</strong></td><td class="mono">${esc(r.metric)}</td><td>${esc(r.operator)}</td><td>${r.warning_threshold??'—'}</td><td>${r.critical_threshold??'—'}</td><td>${r.duration_seconds}s</td><td>${badge(r.enabled?'up':'unknown',r.enabled?'enabled':'disabled')}</td><td><button class="link-button" data-edit-rule="${esc(r.id)}">Edit</button></td></tr>`).join('')}</tbody></table></div></article>`;
  $('#new-rule').onclick=()=>ruleModal(null);
  $$('[data-edit-rule]').forEach(btn=>btn.onclick=()=>ruleModal(rules.find(r=>r.id===btn.dataset.editRule)));
}

function ruleModal(rule) {
  openModal(rule?'Edit monitoring rule':'Create monitoring rule','Threshold rules are evaluated against the latest managed-agent telemetry.',`<form id="rule-form" class="form-stack"><label>Name<input id="rule-name" value="${esc(rule?.name||'')}" required/></label><label>Metric<select id="rule-metric"><option value="sentinel_cpu_usage_percent">CPU utilization</option><option value="sentinel_memory_usage_percent">Memory utilization</option><option value="sentinel_disk_usage_percent">Disk utilization</option><option value="sentinel_agent_up">Managed agent availability</option></select></label><div class="form-grid"><label>Operator<select id="rule-operator"><option>&gt;</option><option>&gt;=</option><option>&lt;</option><option>&lt;=</option></select></label><label>Duration (seconds)<input id="rule-duration" type="number" min="0" value="${rule?.duration_seconds??300}"/></label><label>Warning threshold<input id="rule-warning" type="number" step="any" value="${rule?.warning_threshold??''}"/></label><label>Critical threshold<input id="rule-critical" type="number" step="any" value="${rule?.critical_threshold??''}"/></label></div><label class="checkbox-row"><input id="rule-enabled" type="checkbox" ${rule?.enabled!==false?'checked':''}/>Enabled</label><button class="button primary" type="submit">${rule?'Save rule':'Create rule'}</button></form>`);
  $('#rule-metric').value=rule?.metric||'sentinel_cpu_usage_percent';$('#rule-operator').value=rule?.operator||'>';
  $('#rule-form').onsubmit=async event=>{event.preventDefault();const parse=v=>v===''?null:Number(v);const payload={name:$('#rule-name').value.trim(),metric:$('#rule-metric').value,operator:$('#rule-operator').value,warning_threshold:parse($('#rule-warning').value),critical_threshold:parse($('#rule-critical').value),duration_seconds:Number($('#rule-duration').value),match_labels:{},enabled:$('#rule-enabled').checked};try{if(rule)await api(`/api/v1/rules/${rule.id}`,{method:'PATCH',body:JSON.stringify(payload)});else await api('/api/v1/rules',{method:'POST',body:JSON.stringify(payload)});closeModal();toast(rule?'Rule updated':'Rule created');await renderRules();}catch(e){toast(e.message,true);}};
}

async function renderTopology() {
  const graph=await api('/api/v1/topology/graph');
  content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Infrastructure topology</h2><p>Known topology edges with all monitored hosts rendered as nodes</p></div><div class="panel-actions"><span class="badge info">${graph.nodes.length} nodes</span><span class="badge info">${graph.edges.length} edges</span></div></div>${topologyHtml(graph)}</article>`;
}

async function renderSnmp() {
  const devices=await api('/api/v1/devices?limit=5000');const snmp=devices.filter(d=>d.snmp_enabled);
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>Add SNMP target</h2><p>Register a device for snmp_exporter collection</p></div></div><div class="panel-body"><form id="snmp-form" class="form-stack"><div class="form-grid"><label>IP address<input id="snmp-ip" placeholder="192.168.1.1" required/></label><label>Hostname<input id="snmp-hostname" placeholder="core-switch-01"/></label><label>Site<input id="snmp-site" value="default"/></label><label>Module<select id="snmp-module"><option value="if_mib">if_mib</option></select></label><label>Auth profile<input id="snmp-auth" value="public_v2"/></label><label>Device class<select id="snmp-class"><option value="switch">Switch</option><option value="router">Router</option><option value="firewall">Firewall</option><option value="ups">UPS</option><option value="printer">Printer</option><option value="unknown">Unknown</option></select></label></div><button class="button primary" type="submit">Add SNMP target</button></form></div></article><article class="panel"><div class="panel-head"><div><h2>SNMP architecture</h2><p>Prometheus-native collection</p></div></div><div class="panel-body"><div class="notice">SentinelView stores SNMP target metadata and exposes HTTP service discovery to Prometheus. <strong>snmp_exporter</strong> performs collection. v0.3.0 includes generic <code>if_mib</code>; vendor packs such as APC UPS and Vertiv are catalogued for later profiles.</div></div></article></div><article class="panel"><div class="panel-head"><div><h2>SNMP targets</h2><p>${snmp.length} enabled devices</p></div></div><div class="table-wrap"><table><thead><tr><th>State</th><th>Device</th><th>IP</th><th>Class</th><th>Module</th><th>Auth</th><th>Site</th></tr></thead><tbody>${snmp.map(d=>`<tr class="row-click" data-host-id="${esc(d.id)}"><td>${state(d.state)}</td><td>${esc(d.hostname||'Unknown')}</td><td class="mono">${esc(d.ip_address)}</td><td>${esc(d.device_class)}</td><td>${esc(d.snmp_module)}</td><td>${esc(d.snmp_auth)}</td><td>${esc(d.site||'default')}</td></tr>`).join('')||`<tr><td colspan="7">${empty('No SNMP targets configured.')}</td></tr>`}</tbody></table></div></article></div>`;
  $('#snmp-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/v1/devices',{method:'POST',body:JSON.stringify({ip_address:$('#snmp-ip').value.trim(),hostname:$('#snmp-hostname').value.trim()||null,device_class:$('#snmp-class').value,site:$('#snmp-site').value.trim()||'default',tags:['snmp'],snmp_enabled:true,snmp_module:$('#snmp-module').value,snmp_auth:$('#snmp-auth').value.trim()||'public_v2'})});toast('SNMP target added');await renderSnmp();}catch(e){toast(e.message,true);}};
}

async function renderIntegrations() {
  const rows=await api('/api/v1/integrations');
  content.innerHTML=`<div class="integration-grid">${rows.map(i=>`<article class="integration-card"><div class="integration-head"><div><h3>${esc(i.name)}</h3><div class="integration-category">${esc(i.category)}</div></div>${badge(i.status==='available'?'up':'unknown',i.status)}</div><div class="integration-features">${i.features.map(f=>`<span class="tag">${esc(f)}</span>`).join('')}</div></article>`).join('')}</div>`;
}

async function renderNotifications() {
  const channels=await api('/api/v1/notification-channels');
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>Add notification channel</h2><p>Configuration store for alert routing integrations</p></div></div><div class="panel-body"><form id="channel-form" class="form-stack"><label>Name<input id="channel-name" required placeholder="NOC webhook"/></label><label>Type<select id="channel-type"><option value="webhook">Webhook</option><option value="email">Email</option><option value="slack">Slack</option><option value="teams">Microsoft Teams</option><option value="telegram">Telegram</option></select></label><label>Configuration JSON<textarea id="channel-config" placeholder='{"url":"https://..."}'>{}</textarea></label><button class="button primary" type="submit">Create channel</button></form></div></article><article class="panel"><div class="panel-head"><div><h2>Routing</h2><p>Notification engine status</p></div></div><div class="panel-body"><div class="notice warning">v0.3.0 provides channel management in the first-party UI. Automatic alert dispatch/routing is the next notification-engine phase; channels are not silently used until routing is explicitly implemented.</div></div></article></div><article class="panel"><div class="panel-head"><div><h2>Channels</h2><p>${channels.length} configured</p></div></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Updated</th><th></th></tr></thead><tbody>${channels.map(c=>`<tr><td><strong>${esc(c.name)}</strong></td><td>${esc(c.channel_type)}</td><td>${badge(c.enabled?'up':'unknown',c.enabled?'enabled':'disabled')}</td><td>${fmtDate(c.updated_at)}</td><td><button class="link-button danger" data-delete-channel="${esc(c.id)}">Delete</button></td></tr>`).join('')||`<tr><td colspan="5">${empty('No notification channels configured.')}</td></tr>`}</tbody></table></div></article></div>`;
  $('#channel-form').onsubmit=async event=>{event.preventDefault();try{let config={};try{config=JSON.parse($('#channel-config').value||'{}');}catch{throw new Error('Configuration must be valid JSON');}await api('/api/v1/notification-channels',{method:'POST',body:JSON.stringify({name:$('#channel-name').value.trim(),channel_type:$('#channel-type').value,enabled:true,config})});toast('Notification channel created');await renderNotifications();}catch(e){toast(e.message,true);}};
  $$('[data-delete-channel]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Delete this notification channel?'))return;try{await api(`/api/v1/notification-channels/${btn.dataset.deleteChannel}`,{method:'DELETE'});toast('Channel deleted');await renderNotifications();}catch(e){toast(e.message,true);}});
}

async function renderMaintenance() {
  const [windows,hosts]=await Promise.all([api('/api/v1/maintenance'),api('/api/v1/hosts')]);
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>Schedule maintenance</h2><p>Record planned maintenance windows</p></div></div><div class="panel-body"><form id="maintenance-form" class="form-stack"><label>Name<input id="maint-name" required placeholder="Sunday database maintenance"/></label><div class="form-grid"><label>Host (optional)<select id="maint-host"><option value="">All / use site</option>${hosts.map(h=>`<option value="${esc(h.id)}">${esc(h.hostname||h.ip_address)}</option>`).join('')}</select></label><label>Site (optional)<input id="maint-site" placeholder="hcm-dc"/></label><label>Start<input id="maint-start" type="datetime-local" required/></label><label>End<input id="maint-end" type="datetime-local" required/></label></div><label class="checkbox-row"><input id="maint-suppress" type="checkbox" checked/>Suppress notifications metadata</label><label class="checkbox-row"><input id="maint-sla" type="checkbox" checked/>Exclude from SLA metadata</label><button class="button primary" type="submit">Schedule window</button></form></div></article><article class="panel"><div class="panel-head"><div><h2>Behavior</h2><p>Current implementation boundary</p></div></div><div class="panel-body"><div class="notice">Maintenance windows are fully stored and visible in the operations UI. Problem suppression and SLA exclusion metadata are available to the platform; automated notification routing will consume them when the notification engine is enabled.</div></div></article></div><article class="panel"><div class="panel-head"><div><h2>Maintenance windows</h2><p>${windows.length} scheduled or historical</p></div></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Target</th><th>Start</th><th>End</th><th>Suppress</th><th>SLA exclude</th><th>Created by</th><th></th></tr></thead><tbody>${windows.map(w=>`<tr><td><strong>${esc(w.name)}</strong></td><td>${esc(w.device_id?hostNameById(hosts,w.device_id):w.site||'all')}</td><td>${fmtDate(w.starts_at)}</td><td>${fmtDate(w.ends_at)}</td><td>${badge(w.suppress_notifications?'up':'unknown',w.suppress_notifications?'yes':'no')}</td><td>${badge(w.exclude_from_sla?'up':'unknown',w.exclude_from_sla?'yes':'no')}</td><td>${esc(w.created_by)}</td><td><button class="link-button danger" data-delete-maint="${esc(w.id)}">Delete</button></td></tr>`).join('')||`<tr><td colspan="8">${empty('No maintenance windows.')}</td></tr>`}</tbody></table></div></article></div>`;
  const now=new Date();const later=new Date(now.getTime()+2*3600000);const localInput=d=>new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);$('#maint-start').value=localInput(now);$('#maint-end').value=localInput(later);
  $('#maintenance-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/v1/maintenance',{method:'POST',body:JSON.stringify({name:$('#maint-name').value.trim(),device_id:$('#maint-host').value||null,site:$('#maint-site').value.trim()||null,starts_at:new Date($('#maint-start').value).toISOString(),ends_at:new Date($('#maint-end').value).toISOString(),suppress_notifications:$('#maint-suppress').checked,exclude_from_sla:$('#maint-sla').checked})});toast('Maintenance scheduled');await renderMaintenance();}catch(e){toast(e.message,true);}};
  $$('[data-delete-maint]').forEach(btn=>btn.onclick=async()=>{if(!confirm('Delete maintenance window?'))return;try{await api(`/api/v1/maintenance/${btn.dataset.deleteMaint}`,{method:'DELETE'});toast('Maintenance deleted');await renderMaintenance();}catch(e){toast(e.message,true);}});
}

async function renderAvailability() {
  const [data,slas,hosts]=await Promise.all([api('/api/v1/availability'),api('/api/v1/slas'),api('/api/v1/hosts')]);
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>SLA definitions</h2><p>Service-level objectives over 30-day availability</p></div><button id="new-sla" class="button primary small">+ SLA</button></div><div class="table-wrap"><table><thead><tr><th>Name</th><th>Target</th><th>Current</th><th>Status</th></tr></thead><tbody>${(data.slas||[]).map(s=>`<tr><td><strong>${esc(s.name)}</strong></td><td>${s.target_percent}%</td><td>${s.current_percent==null?'—':s.current_percent+'%'}</td><td>${badge(s.status)}</td></tr>`).join('')||`<tr><td colspan="4">${empty('No SLA definitions yet.')}</td></tr>`}</tbody></table></div></article><article class="panel"><div class="panel-head"><div><h2>History note</h2><p>Availability accounting</p></div></div><div class="panel-body"><div class="notice">${esc(data.history_note)}</div></div></article></div><article class="panel"><div class="panel-head"><div><h2>Host availability</h2><p>Calculated from state-change events</p></div></div><div class="table-wrap"><table><thead><tr><th>Host</th><th>Site</th><th>State</th><th>24h</th><th>7d</th><th>30d</th></tr></thead><tbody>${(data.hosts||[]).map(h=>`<tr class="row-click" data-host-id="${esc(h.device_id)}"><td><div class="primary-cell"><strong>${esc(h.hostname)}</strong><span>${esc(h.ip_address)}</span></div></td><td>${esc(h.site||'default')}</td><td>${badge(h.state)}</td><td>${h.availability_24h}%</td><td>${h.availability_7d}%</td><td>${h.availability_30d}%</td></tr>`).join('')}</tbody></table></div></article></div>`;
  $('#new-sla').onclick=()=>{openModal('Create SLA','Create a target for a host, site or the full monitored estate.',`<form id="sla-form" class="form-stack"><label>Name<input id="sla-name" required placeholder="Production availability"/></label><label>Target percent<input id="sla-target" type="number" min="0" max="100" step="0.001" value="99.95"/></label><label>Host (optional)<select id="sla-host"><option value="">All hosts / use site</option>${hosts.map(h=>`<option value="${esc(h.id)}">${esc(h.hostname||h.ip_address)}</option>`).join('')}</select></label><label>Site (optional)<input id="sla-site"/></label><button class="button primary" type="submit">Create SLA</button></form>`);$('#sla-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/v1/slas',{method:'POST',body:JSON.stringify({name:$('#sla-name').value.trim(),target_percent:Number($('#sla-target').value),device_id:$('#sla-host').value||null,site:$('#sla-site').value.trim()||null,enabled:true})});closeModal();toast('SLA created');await renderAvailability();}catch(e){toast(e.message,true);}};};
}

async function renderUsers() {
  if(appState.user?.role!=='admin'){content.innerHTML=`<div class="notice danger">Administrator role is required to manage users.</div>`;return;}
  const users=await api('/api/v1/users');
  content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Local users</h2><p>v0.3.0 local session authentication and role model</p></div><button class="button primary small" id="new-user">+ User</button></div><div class="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th>Created</th><th></th></tr></thead><tbody>${users.map(u=>`<tr><td><strong>${esc(u.username)}</strong></td><td>${badge('info',u.role)}</td><td>${badge(u.enabled?'up':'down',u.enabled?'enabled':'disabled')}</td><td>${ago(u.last_login)}</td><td>${fmtDate(u.created_at)}</td><td><button class="link-button" data-edit-user="${esc(u.id)}">Edit</button></td></tr>`).join('')}</tbody></table></div></article>`;
  $('#new-user').onclick=()=>userModal(null);$$('[data-edit-user]').forEach(btn=>btn.onclick=()=>userModal(users.find(u=>u.id===btn.dataset.editUser)));
}

function userModal(user) {
  openModal(user?'Edit user':'Create user','Roles: admin, operator and viewer.',`<form id="user-form" class="form-stack"><label>Username<input id="usr-name" value="${esc(user?.username||'')}" ${user?'disabled':''} required/></label><label>${user?'New password (optional)':'Password'}<input id="usr-password" type="password" ${user?'':'required'} minlength="8"/></label><label>Role<select id="usr-role"><option value="admin">Admin</option><option value="operator">Operator</option><option value="viewer">Viewer</option></select></label>${user?`<label class="checkbox-row"><input id="usr-enabled" type="checkbox" ${user.enabled?'checked':''}/>Enabled</label>`:''}<button class="button primary" type="submit">${user?'Save user':'Create user'}</button></form>`);$('#usr-role').value=user?.role||'viewer';$('#user-form').onsubmit=async event=>{event.preventDefault();try{if(user){const payload={role:$('#usr-role').value,enabled:$('#usr-enabled').checked};if($('#usr-password').value)payload.password=$('#usr-password').value;await api(`/api/v1/users/${user.id}`,{method:'PATCH',body:JSON.stringify(payload)});}else{await api('/api/v1/users',{method:'POST',body:JSON.stringify({username:$('#usr-name').value.trim(),password:$('#usr-password').value,role:$('#usr-role').value})});}closeModal();toast(user?'User updated':'User created');await renderUsers();}catch(e){toast(e.message,true);}};
}

async function renderAudit() {
  if(!['admin','operator'].includes(appState.user?.role)){content.innerHTML=`<div class="notice danger">Operator or administrator role is required to view the audit log.</div>`;return;}
  const rows=await api('/api/v1/audit?limit=300');
  content.innerHTML=`<article class="panel"><div class="panel-head"><div><h2>Audit log</h2><p>Administrative and configuration actions</p></div></div><div class="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Object</th><th>Message</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${fmtDate(r.created_at)}</td><td>${esc(r.actor)}</td><td>${badge('info',r.action)}</td><td class="mono">${esc(r.object_type)}${r.object_id?` / ${esc(r.object_id.slice(0,10))}`:''}</td><td>${esc(r.message)}</td></tr>`).join('')||`<tr><td colspan="5">${empty('No audit events yet.')}</td></tr>`}</tbody></table></div></article>`;
}

async function renderSettings() {
  const settings=await api('/api/v1/platform/settings');const host=location.hostname||'localhost';
  content.innerHTML=`<div class="page-stack"><div class="grid-2"><article class="panel"><div class="panel-head"><div><h2>SentinelView platform</h2><p>First-party operations console</p></div>${badge('up',`v${settings.version}`)}</div><div class="panel-body"><div class="kv-grid">${kv('Monitoring UI',settings.monitoring_ui)}${kv('Authentication',settings.authentication)}${kv('Agent online timeout',`${settings.agent_online_seconds}s`)}${kv('Discovery max hosts',settings.scan_max_hosts)}${kv('Prometheus backend',settings.prometheus_url)}${kv('Current user',`${appState.user.username} (${appState.user.role})`)}</div></div></article><article class="panel"><div class="panel-head"><div><h2>Component endpoints</h2><p>Grafana and Prometheus remain available for advanced analysis</p></div></div><div class="panel-body"><div class="form-stack"><a class="button secondary" target="_blank" href="http://${host}:3000">Open Grafana ↗</a><a class="button secondary" target="_blank" href="http://${host}:9090">Open Prometheus ↗</a><a class="button secondary" target="_blank" href="http://${host}:8080/docs">Open API docs ↗</a></div></div></article></div><article class="panel"><div class="panel-head"><div><h2>Feature status</h2><p>Capabilities enabled in this release</p></div></div><div class="panel-body"><div class="integration-features">${Object.entries(settings.features).map(([key,val])=>`<span class="badge ${val?'up':'unknown'}">${esc(key.replaceAll('_',' '))}</span>`).join('')}</div></div></article><article class="panel"><div class="panel-head"><div><h2>Security baseline</h2><p>Recommended production configuration</p></div></div><div class="panel-body"><div class="notice warning">Change the bootstrap UI password, API key, PostgreSQL password, Grafana password and session secret in <code>.env</code>. Put the UI/control API behind HTTPS before using it outside a trusted lab or management VLAN.</div></div></article></div>`;
}

const renderers={overview:renderOverview,hosts:renderHosts,host:renderHost,services:renderServices,problems:renderProblems,events:renderEvents,topology:renderTopology,discovery:renderDiscovery,devices:renderDevices,agents:renderAgents,policies:renderPolicies,rules:renderRules,snmp:renderSnmp,integrations:renderIntegrations,notifications:renderNotifications,maintenance:renderMaintenance,availability:renderAvailability,users:renderUsers,audit:renderAudit,settings:renderSettings};

async function navigateFromHash() {
  const {name,arg}=parseRoute();appState.route=name;appState.routeArg=arg;setPageChrome(name,arg);loading();
  try { await renderers[name](arg); bindGenericActions(); } catch(error) { console.error(error); errorPanel(error); }
}

function bindGenericActions() {
  $$('[data-host-id]').forEach(el=>{el.onclick=event=>{const interactive=event.target.closest('a,button');if(interactive&&interactive!==el)return;location.hash=`host/${el.dataset.hostId}`;};});
  $$('[data-nav]').forEach(btn=>btn.onclick=()=>{location.hash=btn.dataset.nav;});
}

async function globalSearch(query) {
  const root=$('#search-results');if(!query.trim()){root.classList.add('hidden');root.innerHTML='';return;}
  try { const result=await api(`/api/v1/search${qs({q:query.trim()})}`);let html='';if(result.hosts?.length){html+=`<div class="search-group-title">Hosts</div>${result.hosts.map(h=>`<button class="search-result" data-search-host="${esc(h.id)}"><strong>${esc(h.title)}</strong><span>${esc(h.subtitle)}</span></button>`).join('')}`;}if(result.events?.length){html+=`<div class="search-group-title">Events</div>${result.events.map(e=>`<button class="search-result" data-search-host="${esc(e.device_id||'')}"><strong>${esc(e.title)}</strong><span>${esc(e.subtitle)}</span></button>`).join('')}`;}root.innerHTML=html||empty('No results');root.classList.remove('hidden');$$('[data-search-host]',root).forEach(btn=>btn.onclick=()=>{if(btn.dataset.searchHost)location.hash=`host/${btn.dataset.searchHost}`;else location.hash='events';root.classList.add('hidden');$('#global-search').value='';}); } catch { root.classList.add('hidden'); }
}

function quickActions() {
  openModal('Quick actions','Common infrastructure operations',`<div class="form-stack"><button class="button primary" data-quick-nav="discovery">Discover network</button><button class="button secondary" data-quick-nav="agents">Install managed agent</button><button class="button secondary" data-quick-nav="maintenance">Schedule maintenance</button><button class="button secondary" data-quick-nav="rules">Monitoring rules</button></div>`);$$('[data-quick-nav]').forEach(btn=>btn.onclick=()=>{closeModal();location.hash=btn.dataset.quickNav;});
}

$('#login-form').addEventListener('submit',handleLogin);
$('#logout-btn').addEventListener('click',()=>{clearSession();appState.user=null;showLogin();});
$('#refresh-btn').addEventListener('click',()=>navigateFromHash());
$('#quick-add-btn').addEventListener('click',quickActions);
$('#mobile-menu').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
$('#global-search').addEventListener('input',event=>{clearTimeout(appState.searchTimer);appState.searchTimer=setTimeout(()=>globalSearch(event.target.value),180);});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();$('#global-search').focus();}});
document.addEventListener('click',event=>{if(!event.target.closest('.global-search-wrap'))$('#search-results').classList.add('hidden');if(event.target.closest('.nav-item')&&innerWidth<900)$('#sidebar').classList.remove('open');});
window.addEventListener('hashchange',navigateFromHash);
window.addEventListener('sentinel-auth-expired',()=>{toast('Session expired. Sign in again.',true);showLogin();});

(async function boot(){await checkApiHealth();setInterval(checkApiHealth,15000);if(await authenticateExistingSession())await navigateFromHash();})();
