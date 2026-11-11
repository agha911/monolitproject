import WebApp from '@twa-dev/sdk';
import API_BASE_URL from './components/config';

// Shared transport for existing screens, including their direct fetch calls.
const nativeFetch = window.fetch.bind(window);
const apiBase = new URL(API_BASE_URL, window.location.origin);
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
  if (url.origin !== apiBase.origin || !url.pathname.startsWith('/api/')) {
    return nativeFetch(input, init);
  }
  const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
  if (WebApp.initData) headers.set('X-Telegram-Init-Data', WebApp.initData);
  return nativeFetch(input, { ...init, headers });
};
