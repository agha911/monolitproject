import { apiGet, apiPost } from './http';
import WebApp from '../../../telegram';

export type Drop = {
  id: number;
  partner_id: number;
  title: string;
  discount_percent: number;
  start_at: string;
  end_at: string;
  price_coins: number;
  per_user_limit: number;
  total_supply?: number | null;
  active: boolean;
  visible: boolean;
  partner?: { id: number; name: string; slug: string } | null;
};

export type Purchase = {
  id: number;
  user_id: number;
  drop_id: number;
  unique_code: string;
  status: 'active' | 'redeemed' | 'revoked';
  created_at: string;
  redeemed_at?: string | null;
  drop_title?: string | null;
  partner_name?: string | null;
  price_coins?: number | null;
  discount_percent?: number | null;
};

export async function listDrops(): Promise<Drop[]> {
  return apiGet<Drop[]>('/api/drops');
}

export async function buyDrop(dropId: number): Promise<Purchase> {
  const tgId = WebApp?.initDataUnsafe?.user?.id;
  if (!tgId) throw new Error('Telegram user id is missing');

  return apiPost<Purchase>('/api/drops/buy', {
    telegram_id: tgId,
    drop_id: dropId,
  });
}
