const TOKEN_KEY = 'sentinelview.session';
const USER_KEY = 'sentinelview.user';

export function getToken() { return localStorage.getItem(TOKEN_KEY) || ''; }
export function getStoredUser() {
  try { return JSON.parse(localStorage.getItem(USER_KEY) || 'null'); } catch { return null; }
}
export function setSession(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user || null));
}
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && !path.includes('/auth/login')) {
    clearSession();
    window.dispatchEvent(new CustomEvent('sentinel-auth-expired'));
  }
  const text = await response.text();
  let payload = null;
  if (text) {
    try { payload = JSON.parse(text); } catch { payload = text; }
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || (typeof payload === 'string' ? payload : `HTTP ${response.status}`);
    const error = new Error(detail);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export async function login(username, password) {
  return api('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
}

export function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const out = search.toString();
  return out ? `?${out}` : '';
}
