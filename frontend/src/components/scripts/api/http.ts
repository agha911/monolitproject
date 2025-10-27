import WebApp from '@twa-dev/sdk';

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''; // если тот же домен — пусть будет пусто

export function tgHeaders() {
  const tgId = WebApp?.initDataUnsafe?.user?.id;
  return { 'Content-Type': 'application/json', 'X-Telegram-User-Id': String(tgId || '') };
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: tgHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: tgHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
