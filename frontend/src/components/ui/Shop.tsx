import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [clickBoostLevel, setClickBoostLevel] = useState(0);
  const [energyRefillsLeft, setEnergyRefillsLeft] = useState(0);
  const [totalXp, setTotalXp] = useState(0);

  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;

  const fetchUserData = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: WebApp.initData }),
      });
      const data = await res.json();
      setClickBoostLevel(data.click_boost_level ?? 0);
      setEnergyRefillsLeft(data.energy_refills_left ?? 0);
      setTotalXp(data.total_xp ?? 0);
    } catch (err) {
      console.error('Ошибка при загрузке данных пользователя:', err);
    }
  };

  useEffect(() => {
    fetchUserData();
  }, []);

  const handleBuyClickBoost = async () => {
    setLoading(true);
    setMessage('');

    const price = 5000 * Math.pow(2, clickBoostLevel);
    if (clickBoostLevel >= 4) {
      setMessage(t('shop_max_level'));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_click_boost`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        await fetchUserData();
        setMessage(t('shop_success_boost', { value: `x${clickBoostLevel + 1}` }));
      } else {
        setMessage(`${t('shop_error')}: ${data.message}`);
      }
    } catch {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const handleBuyEnergyUpgrade = async () => {
    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_max_energy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        await fetchUserData();
        setMessage(t('shop_success', { value: data.new_max_energy }));
      } else {
        setMessage(`${t('shop_error')}: ${data.message}`);
      }
    } catch {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const handleRefillEnergy = async () => {
    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_energy_refill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        await fetchUserData();
        setMessage(t('refill_success'));
      } else {
        setMessage(`${t('shop_error')}: ${data.message}`);
      }
    } catch {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const clickBoostPrice = 5000 * Math.pow(2, clickBoostLevel);

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-6">🛒 {t('title_shop')}</h2>

      {/* Бустер на клики */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">💥 {t('boost_click')}</h3>
        <p className="text-sm text-[#a0f6ff]">{clickBoostPrice} $GAP ({t('level')}: x{clickBoostLevel + 1})</p>

        <button
          onClick={handleBuyClickBoost}
          disabled={loading || clickBoostLevel >= 4}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>
      </div>

      {/* Увеличение максимальной энергии */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">🔋 {t('energy_upgrade')}</h3>
        <p className="text-sm text-[#a0f6ff]">500 $GAP</p>

        <button
          onClick={handleBuyEnergyUpgrade}
          disabled={loading}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>
      </div>

      {/* Восполнение энергии */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">⚡ {t('refill_energy')}</h3>
        <p className="text-sm text-[#a0f6ff]">500 $GAP</p>
        <p className="text-xs text-[#89dfff]">{t('available')}: {energyRefillsLeft} / 2</p>

        <button
          onClick={handleRefillEnergy}
          disabled={loading || energyRefillsLeft <= 0}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>
      </div>

      {message && <p className="text-sm mt-4 text-center text-[#a0f6ff]">{message}</p>}
    </div>
  );
};

export default Shop;






