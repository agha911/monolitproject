import { apiGet } from './http';
import type { Purchase } from './drops';

export type UserCard = {
  username: string;
  coins: number;          // это User.score
  invited_count: number;
  active_drops: Purchase[];
};

export async function getUserCard(): Promise<UserCard> {
  return apiGet<UserCard>('/api/user/card');
}
