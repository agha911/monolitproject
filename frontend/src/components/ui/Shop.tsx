import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;

  const handleBuyEnergyUpgrade = async () => {
    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_max_energy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'success') {
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
        body: JSON.stringify({ user_id: telegramUserId }),
      });

      const data = await res.json();
      if (data.status === 'success') {
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

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-6">🛒 {t('title_shop')}</h2>

      {/* Увеличение максимальной энергии */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">🔋 {t('energy_upgrade')}</h3>
        <p className="text-sm text-[#a0f6ff]">50 $GAP</p>

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

        <button
          onClick={handleRefillEnergy}
          disabled={loading}
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


