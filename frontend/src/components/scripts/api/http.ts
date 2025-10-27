// src/scripts/api/http.ts
import WebApp from '@twa-dev/sdk';
import API_BASE_URL from '../../config'; // 👈 берём общий конфиг

const API_BASE = API_BASE_URL || ''; // если один домен/прокси — оставь пусто

export function tgHeaders() {
  const tgId = WebApp?.initDataUnsafe?.user?.id;
  return {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    'X-Telegram-User-Id': String(tgId ?? ''),
  };
}

async function parseJsonOrThrow(res: Response) {
  const ct = res.headers.get('content-type') || '';
  const body = await res.text();
  if (!res.ok) throw new Error(body || `HTTP ${res.status} @ ${res.url}`);
  if (!ct.includes('application/json')) {
    throw new Error(`Bad response (content-type: ${ct || 'unknown'}) @ ${res.url}. Body: ${body.slice(0,160)}`);
  }
  return JSON.parse(body);
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: tgHeaders() });
  return parseJsonOrThrow(res) as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: tgHeaders(),
    body: JSON.stringify(body),
  });
  return parseJsonOrThrow(res) as Promise<T>;
}

