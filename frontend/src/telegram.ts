import Telegram from '@twa-dev/sdk';
import API_BASE_URL from './components/config';

export const isDemo = import.meta.env.VITE_DEMO_MODE === 'true';
let demoData = '';
let demoUser: typeof Telegram.initDataUnsafe.user;

export async function initializeDemo() {
  if (!isDemo) return;
  const response = await fetch(`${API_BASE_URL}/demo/session`);
  if (!response.ok) throw new Error('Demo server unavailable. Please try again later.');
  const session: { init_data: string; telegram_id: number; name: string } = await response.json();
  demoData = session.init_data;
  demoUser = { id: session.telegram_id, first_name: session.name, language_code: 'en' };
}

export function showDemoNotice(message = 'Telegram sharing and purchases are unavailable in this browser demo.') {
  window.dispatchEvent(new CustomEvent('demo-notice', { detail: message }));
}

// Existing screens use the same SDK contract. Production always uses the real SDK.
const WebApp: typeof Telegram = isDemo ? new Proxy(Telegram, {
  get(target, property) {
    if (property === 'initData') return demoData;
    if (property === 'initDataUnsafe') return { user: demoUser };
    if (property === 'ready' || property === 'expand') return () => undefined;
    if (property === 'openTelegramLink' || property === 'openInvoice') return () => showDemoNotice();
    if (property === 'showPopup') return (params: { message: string }) => showDemoNotice(params.message);
    if (property === 'HapticFeedback') return {
      impactOccurred: () => undefined, notificationOccurred: () => undefined, selectionChanged: () => undefined,
    };
    return Reflect.get(target, property);
  },
}) : Telegram;

export default WebApp;
