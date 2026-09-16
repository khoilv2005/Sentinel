import { api } from './api.js';
import { $, badge, empty, esc, fmtDate, toast } from './ui.js';

const root = $('#page-content');
let scheduled = false;
let running = false;

const DOMAIN_GROUPS = {
  assets: { parent: 'hosts', title: 'Assets', routes: [['hosts','All assets'],['services','Services'],['topology','Topology'],['discovery','Discover'],['devices','Inventory details']] },
  monitoring: { parent: 'agents', title: 'Monitoring', routes: [['agents','Managed agent'],['agentless','Remote collectors'],['credentials','Credentials'],['policies','Agent settings']] },
  alerts: { parent: 'rules', title: 'Alerts', routes: [['rules','Rules'],['notifications','Notifications'],['maintenance','Maintenance']] },
  settings: { parent: 'settings', title: 'Settings', routes: [['settings','Platform'],['integrations','Capabilities'],['snmp','Legacy SNMP exporter']] },
};

const ROUTE_TO_DOMAIN = Object.fromEntries(Object.entries(DOMAIN_GROUPS).flatMap(([key, group]) => group.routes.map(([route]) => [route, { key, ...group }])));

function routeName() { return (location.hash || '#overview').slice(1).split('/')[0]; }
function navItem(route) { return document.querySelector(`.nav-item[data-route="${route}"]`); }
function setNavLabel(route, text) { const label = navItem(route)?.querySelector('span:nth-child(2)'); if (label) label.textContent = text; }

function consolidateNavigation() {
  setNavLabel('overview','Dashboard');
  setNavLabel('hosts','Assets');
  setNavLabel('events','Operational Events');
  setNavLabel('agents','Monitoring');
  setNavLabel('rules','Alerts');
  setNavLabel('users','Access');
  setNavLabel('audit','Audit');
  ['services','topology','discovery','devices','agentless','policies','credentials','snmp','integrations','notifications','maintenance'].forEach(route => navItem(route)?.classList.add('hidden'));
  const route = routeName();
  const domain = ROUTE_TO_DOMAIN[route];
  if (domain) {
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
    navItem(domain.parent)?.classList.add('active');
  }
}

function ensureStyles() {
  if (document.getElementById('sentinel-runtime-enhancement-style')) return;
  const style = document.createElement('style');
  style.id = 'sentinel-runtime-enhancement-style';
  style.textContent = '.badge.suppressed{background:#202936;border-color:#41526a;color:#a9c5e8}.badge.degraded{background:#312713;border-color:#5a4820;color:#f4c96d}.state-dot.degraded{background:var(--yellow)}.delivery-error{max-width:420px;white-space:normal;overflow-wrap:anywhere}.domain-tabs{display:flex;gap:6px;flex-wrap:wrap;padding:10px 12px;margin-bottom:14px;border:1px solid var(--border);border-radius:10px;background:var(--panel,#111827)}.domain-tab{display:inline-flex;align-items:center;padding:7px 10px;border-radius:7px;text-decoration:none;color:inherit;border:1px solid transparent;font-size:13px;font-weight:600}.domain-tab:hover{border-color:var(--border)}.domain-tab.active{background:rgba(96,165,250,.12);border-color:rgba(96,165,250,.35);color:#bfdbfe}';
  document.head.appendChild(style);
}

function replacePanelCopy(heading, subtitle, noticeText = null) {
  for (const article of root.querySelectorAll('article.panel')) {
    const title = article.querySelector('h2');
    if (!title || title.textContent.trim() !== heading) continue;
    const subtitleNode = title.parentElement?.querySelector('p');
    if (subtitleNode && subtitle) subtitleNode.textContent = subtitle;
    if (noticeText) {
      const notice = article.querySelector('.notice');
      if (notice) { notice.classList.remove('warning'); notice.textContent = noticeText; }
    }
  }
}

function ensureDomainTabs() {
  const route = routeName();
  const domain = ROUTE_TO_DOMAIN[route];
  document.getElementById('sentinel-domain-tabs')?.remove();
  if (!domain || !root) return;
  const tabs = document.createElement('nav');
  tabs.id = 'sentinel-domain-tabs';
  tabs.className = 'domain-tabs';
  tabs.setAttribute('aria-label', `${domain.title} sections`);
  tabs.innerHTML = domain.routes.map(([target,label]) => `<a class="domain-tab ${target===route?'active':''}" href="#${esc(target)}">${esc(label)}</a>`).join('');
  root.prepend(tabs);
  const pageTitle = $('#page-title');
  const pageSubtitle = $('#page-subtitle');
  if (pageTitle) pageTitle.textContent = domain.title;
  if (pageSubtitle) {
    const label = domain.routes.find(([target]) => target === route)?.[1] || '';
    pageSubtitle.textContent = `${label} · consolidated ${domain.title.toLowerCase()} workflow`;
  }
}

async function enhanceDashboard() {
  const cards = [...root.querySelectorAll('.stat-card')];
  const assetCard = cards.find(card => card.querySelector('.stat-label')?.textContent.trim() === 'Hosts');
  if (!assetCard) return;
  try {
    const devices = await api('/api/v1/devices?limit=5000');
    const counts = devices.reduce((acc, device) => {
      const key = ['up','degraded','down'].includes(device.state) ? device.state : 'unknown';
      acc[key] += 1;
      return acc;
    }, { up:0, degraded:0, down:0, unknown:0 });
    assetCard.querySelector('.stat-label').textContent = 'Assets';
    assetCard.querySelector('.stat-value').textContent = String(devices.length);
    assetCard.querySelector('.stat-detail').textContent = `${counts.up} up · ${counts.degraded} degraded · ${counts.down} down · ${counts.unknown} unknown`;
    assetCard.classList.remove('green','yellow','red');
    assetCard.classList.add(counts.down ? 'red' : counts.degraded ? 'yellow' : 'green');
  } catch (error) {
    console.warn('Could not enhance Dashboard asset health', error);
  }
}

function enhanceAssets() {
  const stateFilter = $('#hosts-state');
  if (stateFilter && !stateFilter.querySelector('option[value="degraded"]')) {
    const option = document.createElement('option');
    option.value = 'degraded';
    option.textContent = 'Degraded';
    stateFilter.insertBefore(option, stateFilter.querySelector('option[value="unknown"]'));
  }
  const panelTitle = root.querySelector('.panel-head h2');
  if (panelTitle?.textContent.trim() === 'Hosts') panelTitle.textContent = 'Assets';
  const monitoredCopy = root.querySelector('.panel-head p');
  if (monitoredCopy?.textContent.includes('monitored assets')) monitoredCopy.textContent = monitoredCopy.textContent.replace('monitored assets','infrastructure assets');
}

async function enhanceNotifications() {
  $('#page-subtitle').textContent = 'Notification channels, automatic delivery and routing status';
  replacePanelCopy('Add notification channel','Webhook, Slack, Teams, Telegram or SMTP delivery');
  replacePanelCopy('Routing','Notification delivery engine','Problem open, escalation, recovery and post-maintenance transitions are queued automatically. Failed deliveries use bounded retry; active maintenance can suppress delivery.');
  let deliveries=[];
  try { deliveries=await api('/api/v1/notification-deliveries?limit=50'); } catch(error) { console.warn('Notification delivery history unavailable',error); }
  root.querySelectorAll('[data-delete-channel]').forEach(deleteButton=>{
    const id=deleteButton.dataset.deleteChannel; const cell=deleteButton.closest('td');
    if(!cell||cell.querySelector(`[data-test-channel="${CSS.escape(id)}"]`))return;
    const button=document.createElement('button'); button.className='link-button'; button.type='button'; button.dataset.testChannel=id; button.textContent='Test'; button.style.marginRight='8px';
    button.onclick=async()=>{button.disabled=true;try{const result=await api(`/api/v1/notification-channels/${encodeURIComponent(id)}/test`,{method:'POST'});toast(`Test delivery: ${result.status}`);scheduleEnhancement();}catch(error){toast(error.message,true);}finally{button.disabled=false;}};
    cell.insertBefore(button,deleteButton);
  });
  document.getElementById('notification-delivery-panel')?.remove();
  const panel=document.createElement('article'); panel.className='panel'; panel.id='notification-delivery-panel';
  const rows=deliveries.map(delivery=>`<tr><td>${badge(delivery.status)}</td><td>${esc(delivery.transition)}</td><td>${esc(delivery.severity)}</td><td class="mono">${esc(delivery.channel_id||'—')}</td><td>${Number(delivery.attempts||0)}</td><td class="delivery-error">${esc(delivery.last_error||'—')}</td><td>${fmtDate(delivery.created_at)}</td></tr>`).join('')||`<tr><td colspan="7">${empty('No notification deliveries yet.')}</td></tr>`;
  panel.innerHTML=`<div class="panel-head"><div><h2>Recent deliveries</h2><p>Last 50 queued, sent, suppressed or failed notifications</p></div><button class="button ghost small" id="refresh-deliveries" type="button">Refresh</button></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>Transition</th><th>Severity</th><th>Channel ID</th><th>Attempts</th><th>Last error</th><th>Created</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  root.appendChild(panel); $('#refresh-deliveries')?.addEventListener('click',()=>scheduleEnhancement());
}

function enhanceMaintenance() {
  $('#page-subtitle').textContent='Scheduled problem suppression and SLA exclusions';
  replacePanelCopy('Schedule maintenance','Suppress matching problem notifications and optionally exclude the window from SLA accounting');
  replacePanelCopy('Behavior','Active maintenance engine','Active host, site or global maintenance windows suppress matching problem notifications when requested. Windows marked for SLA exclusion are removed from the eligible availability denominator.');
  for(const label of root.querySelectorAll('label.checkbox-row')){
    const text=label.textContent.trim();
    if(text.includes('Suppress notifications metadata')){const input=label.querySelector('input');label.textContent='';if(input)label.appendChild(input);label.append('Suppress problem notifications');}
    else if(text.includes('Exclude from SLA metadata')){const input=label.querySelector('input');label.textContent='';if(input)label.appendChild(input);label.append('Exclude from SLA accounting');}
  }
}

function enhanceAvailability(){ $('#page-subtitle').textContent='Maintenance-aware availability history and service-level targets'; for(const cell of root.querySelectorAll('td')){if(cell.textContent.trim()==='null%'||cell.textContent.trim()==='undefined%')cell.textContent='—';} }
function enhanceDiscovery(){ replacePanelCopy('Network discovery','Find assets only; monitoring and health are configured separately'); }
function enhanceRemoteCollectors(){ replacePanelCopy('Agentless monitoring','Assign remote monitoring methods to assets that already exist in inventory'); const notice=[...root.querySelectorAll('.notice')].find(node=>node.textContent.includes('WinRM')); if(notice)notice.innerHTML='<strong>Remote collectors</strong> use WinRM, SSH or SNMP against existing Assets. Discovery creates inventory; monitoring assignments collect health and performance. Sentinel Agent remains an optional enhanced method.'; }
function enhanceLegacySnmp(){ replacePanelCopy('Add SNMP target','Legacy snmp_exporter compatibility target'); const notice=[...root.querySelectorAll('.notice')].find(node=>node.textContent.includes('snmp_exporter')); if(notice)notice.innerHTML='<strong>Compatibility view.</strong> New SNMP monitoring should be configured under Monitoring → Remote collectors. This page remains temporarily for existing Prometheus snmp_exporter target metadata and will be removed after migration.'; }

async function applyEnhancements(){
  if(running||!root)return;
  running=true;
  try{
    ensureStyles();
    consolidateNavigation();
    ensureDomainTabs();
    const route=routeName();
    if(route==='overview') await enhanceDashboard();
    else if(route==='hosts') enhanceAssets();
    else if(route==='notifications') await enhanceNotifications();
    else if(route==='maintenance') enhanceMaintenance();
    else if(route==='availability') enhanceAvailability();
    else if(route==='discovery') enhanceDiscovery();
    else if(route==='agentless') enhanceRemoteCollectors();
    else if(route==='snmp') enhanceLegacySnmp();
  }finally{running=false;}
}
function scheduleEnhancement(){if(scheduled)return;scheduled=true;setTimeout(async()=>{scheduled=false;await applyEnhancements();},50);}
if(root)new MutationObserver(()=>scheduleEnhancement()).observe(root,{childList:true,subtree:true});
window.addEventListener('hashchange',scheduleEnhancement);window.addEventListener('load',scheduleEnhancement);scheduleEnhancement();
