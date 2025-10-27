import WebApp from '@twa-dev/sdk';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

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
  const text = await res.text();
  if (!res.ok) {
    // сервер вернул ошибку — пробуем показать тело
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (!ct.includes('application/json')) {
    // это и есть твой случай с <!DOCTYPE …>
    throw new Error(`Bad response (content-type: ${ct || 'unknown'}). Body: ${text.slice(0, 160)}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error('Response is not valid JSON');
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: tgHeaders(), credentials: 'include' as RequestCredentials });
  return parseJsonOrThrow(res) as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: tgHeaders(),
    body: JSON.stringify(body),
    credentials: 'include' as RequestCredentials,
  });
  return parseJsonOrThrow(res) as Promise<T>;
}
