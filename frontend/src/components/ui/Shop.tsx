import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const handleBuyEnergyUpgrade = async () => {
    setLoading(true);
    setMessage('');
    try {
      const res = await fetch('http://localhost:8000/api/shop/buy_max_energy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 123456, // Заменить на telegramUserId
        }),
      });

      const data = await res.json();
      if (data.status === 'success') {
        setMessage(t('shop_success', { value: data.new_max_energy }));
      } else {
        setMessage(`${t('shop_error')}: ${data.message}`);
      }
    } catch (error) {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-6">🛒 {t('title_shop')}</h2>

      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">🔋 {t('energy_upgrade')}</h3>
        <p className="text-sm text-[#a0f6ff]">50 $MONO</p>

        <button
          onClick={handleBuyEnergyUpgrade}
          disabled={loading}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>

        {message && <p className="text-sm mt-2 text-[#a0f6ff]">{message}</p>}
      </div>
    </div>
  );
};

export default Shop;

