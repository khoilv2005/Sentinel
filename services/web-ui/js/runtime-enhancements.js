import { api } from './api.js';
import { $, badge, empty, esc, fmtDate, toast } from './ui.js';

const root = $('#page-content');
let scheduled = false;
let running = false;

function routeName() {
  return (location.hash || '#overview').slice(1).split('/')[0];
}

function ensureStyles() {
  if (document.getElementById('sentinel-runtime-enhancement-style')) return;
  const style = document.createElement('style');
  style.id = 'sentinel-runtime-enhancement-style';
  style.textContent = '.badge.suppressed{background:#202936;border-color:#41526a;color:#a9c5e8}.delivery-error{max-width:420px;white-space:normal;overflow-wrap:anywhere}';
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
      if (notice) {
        notice.classList.remove('warning');
        notice.textContent = noticeText;
      }
    }
  }
}

async function enhanceNotifications() {
  $('#page-subtitle').textContent = 'Notification channels, automatic delivery and routing status';
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

  const old = document.getElementById('notification-delivery-panel');
  if (old) old.remove();
  const panel = document.createElement('article');
  panel.className = 'panel';
  panel.id = 'notification-delivery-panel';
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
  panel.innerHTML = `<div class="panel-head"><div><h2>Recent deliveries</h2><p>Last 50 queued, sent, suppressed or failed notifications</p></div><button class="button ghost small" id="refresh-deliveries" type="button">Refresh</button></div><div class="table-wrap"><table><thead><tr><th>Status</th><th>Transition</th><th>Severity</th><th>Channel ID</th><th>Attempts</th><th>Last error</th><th>Created</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  root.appendChild(panel);
  $('#refresh-deliveries')?.addEventListener('click', () => scheduleEnhancement());
}

function enhanceMaintenance() {
  $('#page-subtitle').textContent = 'Scheduled problem suppression and SLA exclusions';
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
  $('#page-subtitle').textContent = 'Maintenance-aware availability history and service-level targets';
  for (const cell of root.querySelectorAll('td')) {
    if (cell.textContent.trim() === 'null%' || cell.textContent.trim() === 'undefined%') {
      cell.textContent = '—';
    }
  }
}

async function applyEnhancements() {
  if (running || !root) return;
  running = true;
  try {
    ensureStyles();
    const route = routeName();
    if (route === 'notifications') await enhanceNotifications();
    else if (route === 'maintenance') enhanceMaintenance();
    else if (route === 'availability') enhanceAvailability();
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
