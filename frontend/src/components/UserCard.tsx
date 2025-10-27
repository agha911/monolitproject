import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getUserCard, type UserCard as IUserCard } from './scripts/api/user';

type Props = { onClose: () => void };

const UserCard: React.FC<Props> = ({ onClose }) => {
  const { t } = useTranslation();
  const [data, setData] = useState<IUserCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      alert(t('alerts.copied'));
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      alert(t('alerts.copied'));
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const res = await getUserCard();
        setData(res);
      } catch (e: any) {
        setErr(e?.message || t('errors.loadFailed'));
      } finally {
        setLoading(false);
      }
    })();
  }, [t]);

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-end">
      <div className="w-full rounded-t-2xl bg-white text-black p-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-2">
          <div className="text-lg font-semibold">{t('userCard.title')}</div>
          <button className="text-sm px-2 py-1 rounded bg-gray-200" onClick={onClose}>
            {t('actions.close')}
          </button>
        </div>

        {loading && <div>{t('common.loading')}</div>}
        {err && <div className="text-red-600">{err}</div>}

        {data && (
          <>
            <div className="rounded-xl p-3 bg-gray-100 mb-3">
              <div className="text-sm opacity-70">{t('userCard.profile')}</div>
              <div className="text-xl font-semibold">
                {t('userCard.username', { username: data.username })}
              </div>
              <div className="mt-1 text-sm">
                {t('userCard.coins', { count: data.coins })}
              </div>
              <div className="mt-1 text-sm">
                {t('userCard.invited', { count: data.invited_count })}
              </div>
            </div>

            <div className="text-base font-semibold mb-2">{t('userCard.myDrops')}</div>
            {data.active_drops.length === 0 && (
              <div className="text-sm opacity-70">{t('userCard.empty')}</div>
            )}

            <div className="space-y-2">
              {data.active_drops.map((p) => (
                <div key={p.id} className="rounded-xl p-3 bg-gray-100 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">{p.drop_title || t('userCard.dropFallback')}</div>
                    <div className="text-xs opacity-75">
                      {t('userCard.partnerLine', {
                        partner: p.partner_name || '—',
                        percent: p.discount_percent ?? '-',
                      })}
                    </div>
                    <div className="text-xs mt-1">
                      {t('userCard.codeLine', { code: p.unique_code })}
                    </div>
                  </div>
                  <button
                    className="px-3 py-1 rounded-lg bg-black text-white text-sm"
                    onClick={() => copy(p.unique_code)}
                    aria-label={t('actions.copy')}
                    title={t('actions.copy')}
                  >
                    {t('actions.copy')}
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
