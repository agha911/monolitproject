import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [maxEnergy, setMaxEnergy] = useState<number | null>(null);

  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;

  const fetchUserProgress = async () => {
    if (!telegramUserId) return;

    try {
      const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: WebApp.initData })
      });
      const data = await res.json();
      setMaxEnergy(data.max_energy || 100);
    } catch (error) {
      console.error('Ошибка при загрузке прогресса:', error);
    }
  };

  useEffect(() => {
    fetchUserProgress();
  }, [telegramUserId]);

  const calculateEnergyPrice = (currentMax: number) => {
    return 50 + Math.floor((currentMax - 100) / 100) * 25;
  };

  const handleBuyEnergyUpgrade = async () => {
    setLoading(true);
    setMessage('');

    if (!telegramUserId) {
      setMessage('Ошибка: пользователь не определён. Открой приложение через Telegram.');
      setLoading(false);
      return;
    }

    if (!maxEnergy || maxEnergy >= 1200) {
      setMessage(t('shop_max_limit'));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_max_energy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: telegramUserId })
      });

      const data = await res.json();
      if (data.status === 'success') {
        setMessage(t('shop_success', { value: data.new_max_energy }));
        setMaxEnergy(data.new_max_energy);
      } else {
        setMessage(`${t('shop_error')}: ${data.message}`);
      }
    } catch (error) {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const price = maxEnergy !== null ? calculateEnergyPrice(maxEnergy) : 50;
  const isMaxReached = maxEnergy !== null && maxEnergy >= 1200;

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-6">🛒 {t('title_shop')}</h2>

      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">🔋 {t('energy_upgrade')}</h3>
        <p className="text-sm text-[#a0f6ff]">{price} $GAP</p>

        <button
          onClick={handleBuyEnergyUpgrade}
          disabled={loading || isMaxReached}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : isMaxReached ? t('shop_max_limit') : t('buy')}
        </button>

        {message && <p className="text-sm mt-2 text-[#a0f6ff]">{message}</p>}
      </div>
    </div>
  );
};

export default Shop;


