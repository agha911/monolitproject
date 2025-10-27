import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from './config';
import WebApp from '@twa-dev/sdk';

type Props = { onClose: () => void };

type Purchase = {
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

type IUserCard = {
  username: string;
  coins: number;           // на бэке это total_xp/score
  invited_count: number;
  active_drops: Purchase[];
};

const UserCard: React.FC<Props> = ({ onClose }) => {
  const { t } = useTranslation();
  const [data, setData] = useState<IUserCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      alert(t('alerts.copied', { defaultValue: 'ID скопирован' }));
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert(t('alerts.copied', { defaultValue: 'ID скопирован' }));
      } catch {}
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const tgId = WebApp?.initDataUnsafe?.user?.id;
        if (!tgId) throw new Error('Telegram user id is missing');

        const url = `${API_BASE_URL}/api/user/card?telegram_id=${encodeURIComponent(String(tgId))}`;
        const res = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
        const json: IUserCard = await res.json();
        setData(json);
      } catch (e: any) {
        setErr(e?.message || t('errors.loadFailed', { defaultValue: 'Ошибка загрузки' }));
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end">
      <div className="w-full rounded-t-2xl bg-white text-black p-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <div className="text-lg font-semibold">
            {t('userCard.title', { defaultValue: 'Карта пользователя' })}
          </div>
          <button className="text-sm px-2 py-1 rounded bg-gray-200" onClick={onClose}>
            {t('actions.close', { defaultValue: 'Закрыть' })}
          </button>
        </div>

        {loading && <div>{t('common.loading', { defaultValue: 'Загрузка…' })}</div>}
        {err && <div className="text-red-600 break-words">{err}</div>}

        {data && (
          <>
            <div className="rounded-xl p-3 bg-gray-100 mb-3">
              <div className="text-sm opacity-70">
                {t('userCard.profile', { defaultValue: 'Профиль' })}
              </div>
              <div className="text-xl font-semibold">
                {t('userCard.username', {
                  username: data.username,
                  defaultValue: `@${data.username}`,
                })}
              </div>
              <div className="mt-1 text-sm">
                {t('userCard.coins', {
                  count: data.coins,
                  defaultValue: `Монеты: ${data.coins}`,
                })}
              </div>
              <div className="mt-1 text-sm">
                {t('userCard.invited', {
                  count: data.invited_count,
                  defaultValue: `Приглашено друзей: ${data.invited_count}`,
                })}
              </div>
            </div>

            <div className="text-base font-semibold mb-2">
              {t('userCard.myDrops', { defaultValue: 'Мои дропы' })}
            </div>
            {data.active_drops.length === 0 && (
              <div className="text-sm opacity-70">
                {t('userCard.empty', { defaultValue: 'Пока нет активных дропов.' })}
              </div>
            )}

            <div className="space-y-2">
              {data.active_drops.map((p) => (
                <div
                  key={p.id}
                  className="rounded-xl p-3 bg-gray-100 flex items-center justify-between"
                >
                  <div>
                    <div className="text-sm font-medium">
                      {p.drop_title || t('userCard.dropFallback', { defaultValue: 'Дроп' })}
                    </div>
                    <div className="text-xs opacity-75">
                      {t('userCard.partnerLine', {
                        partner: p.partner_name || '—',
                        percent: p.discount_percent ?? '-',
                        defaultValue: `Партнёр: ${p.partner_name || '—'} · Скидка: ${p.discount_percent ?? '-'}%`,
                      })}
                    </div>
                    <div className="text-xs mt-1">
                      {t('userCard.codeLine', {
                        code: p.unique_code,
                        defaultValue: `ID: ${p.unique_code}`,
                      })}
                    </div>
                  </div>
                  <button
                    className="px-3 py-1 rounded-lg bg-black text-white text-sm"
                    onClick={() => copy(p.unique_code)}
                    aria-label={t('actions.copy', { defaultValue: 'Копировать' })}
                    title={t('actions.copy', { defaultValue: 'Копировать' })}
                  >
                    {t('actions.copy', { defaultValue: 'Копировать' })}
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default UserCard;


