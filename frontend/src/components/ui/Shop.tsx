import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

const ENERGY_UPGRADE_PRICE = 2500; // должен совпадать с беком
const REFILL_PRICE = 2500;         // должен совпадать с беком

// Временный сток для предпросмотра (позже можно подменить данными с бэка)
const TSHIRT_TOTAL = 10;
const TSHIRT_LEFT = 10;

const INVITE_REQUIREMENTS: Record<number, number> = {
  6: 1,
  7: 5,
  8: 10,
  9: 15,
  10: 20,
};
const MAX_BOOST_LEVEL = 10;

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // user basics
  const [clickBoostLevel, setClickBoostLevel] = useState(0);
  const [totalXp, setTotalXp] = useState(0);
  const [totalSpent, setTotalSpent] = useState(0);
  const [invitesCount, setInvitesCount] = useState(0);

  // upgrade max energy status
  const [energyUpgradeLimit, setEnergyUpgradeLimit] = useState<number | null>(null);
  const [energyUpgradesLeft, setEnergyUpgradesLeft] = useState<number | null>(null);
  const [userMaxEnergy, setUserMaxEnergy] = useState<number | null>(null);
  const [maxEnergyCap, setMaxEnergyCap] = useState<number | null>(null);

  // refill status
  const [refillLimit, setRefillLimit] = useState<number | null>(null);
  const [refillsLeft, setRefillsLeft] = useState<number | null>(null);
  const [currentEnergy, setCurrentEnergy] = useState<number | null>(null);
  const [refillMaxEnergy, setRefillMaxEnergy] = useState<number | null>(null);

  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;
  const initData = WebApp.initData;

  // ------- loaders -------
  const fetchUserData = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/game/progress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData }),
      });
      const data = await res.json();
      setClickBoostLevel(data.click_boost_level ?? 0);
      setTotalXp(data.total_xp ?? 0);
      if (typeof data.max_energy === 'number') setUserMaxEnergy(data.max_energy);
      if (typeof data.energy === 'number') setCurrentEnergy(data.energy);
    } catch (err) {
      console.error('Ошибка при загрузке данных пользователя:', err);
    }
  };

  const fetchInvitesCount = async () => {
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/user/invites?init_data=${encodeURIComponent(initData)}`
      );
      const data = await res.json();
      setInvitesCount(Number(data?.count ?? 0));
    } catch (err) {
      console.error('Ошибка при получении количества приглашённых:', err);
    }
  };

  const fetchTotalSpent = async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/stats/total-spent`);
      const data = await res.json();
      setTotalSpent(data.total_spent ?? 0);
    } catch (err) {
      console.error('Ошибка при получении общей суммы трат:', err);
    }
  };

  const fetchEnergyUpgradeStatus = async () => {
    if (!telegramUserId) return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/shop/buy_max_energy/status?telegram_id=${telegramUserId}`
      );
      if (!res.ok) return;
      const data = await res.json();
      const limit = Number(data.limit ?? 0);
      const used = Number(data.upgrades_today ?? 0);
      setEnergyUpgradeLimit(limit);
      setEnergyUpgradesLeft(Math.max(0, limit - used));
      if (typeof data.max_energy === 'number') setUserMaxEnergy(data.max_energy);
      if (typeof data.max_energy_cap === 'number') setMaxEnergyCap(data.max_energy_cap);
    } catch (err) {
      console.error('Ошибка статуса апгрейда max energy:', err);
    }
  };

  const fetchRefillStatus = async () => {
    if (!telegramUserId) return;
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/shop/buy_energy_refill/status?telegram_id=${telegramUserId}`
      );
      if (!res.ok) return;
      const data = await res.json();
      const limit = Number(data.limit ?? 0);
      const used = Number(data.refills_today ?? 0);
      setRefillLimit(limit);
      setRefillsLeft(Math.max(0, limit - used));
      if (typeof data.current_energy === 'number') setCurrentEnergy(data.current_energy);
      if (typeof data.max_energy === 'number') setRefillMaxEnergy(data.max_energy);
    } catch (err) {
      console.error('Ошибка статуса рефилла:', err);
    }
  };

  useEffect(() => {
    fetchUserData();
    fetchInvitesCount();
    fetchTotalSpent();
    fetchEnergyUpgradeStatus();
    fetchRefillStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ------- helpers -------
  const nextBoostLevel = Math.min(clickBoostLevel + 1, MAX_BOOST_LEVEL);
  const requiredInvites = INVITE_REQUIREMENTS[nextBoostLevel] ?? 0;
  const clickBoostPrice = 5000 * Math.pow(2, clickBoostLevel);

  // ------- actions -------
  const handleBuyClickBoost = async () => {
    setLoading(true);
    setMessage('');

    if (clickBoostLevel >= MAX_BOOST_LEVEL) {
      setMessage(t('shop_max_level'));
      setLoading(false);
      return;
    }

    if (requiredInvites > 0 && invitesCount < requiredInvites) {
      setMessage(
        t('boost_invites_required', {
          level: `x${nextBoostLevel}`,
          need: requiredInvites,
          have: invitesCount,
        })
      );
      setLoading(false);
      return;
    }

    if (totalXp < clickBoostPrice) {
      setMessage(t('shop_error'));
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
        await fetchTotalSpent();
        await fetchInvitesCount();
        setMessage(t('shop_success_boost', { value: `x${clickBoostLevel + 1}` }));
      } else {
        setMessage(`${t('shop_error')}: ${data.message ?? ''}`);
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

    if (totalXp < ENERGY_UPGRADE_PRICE) {
      setMessage(t('shop_error'));
      setLoading(false);
      return;
    }
    if (energyUpgradesLeft !== null && energyUpgradesLeft <= 0) {
      setMessage(t('shop_error'));
      setLoading(false);
      return;
    }
    if (maxEnergyCap !== null && userMaxEnergy !== null && userMaxEnergy >= maxEnergyCap) {
      setMessage(t('max_energy_reached'));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_max_energy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: telegramUserId }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        await fetchUserData();
        await fetchTotalSpent();
        if (typeof data.limit === 'number' && typeof data.upgrades_today === 'number') {
          setEnergyUpgradeLimit(data.limit);
          setEnergyUpgradesLeft(Math.max(0, data.limit - data.upgrades_today));
        } else {
          await fetchEnergyUpgradeStatus();
        }
        setMessage(t('shop_success', { value: data.new_max_energy }));
      } else {
        setMessage(`${t('shop_error')}: ${data.message ?? ''}`);
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

    const isFull =
      currentEnergy !== null &&
      (refillMaxEnergy ?? userMaxEnergy ?? 0) > 0 &&
      currentEnergy >= (refillMaxEnergy ?? userMaxEnergy ?? 0);

    if (isFull) {
      setMessage(t('shop_restored'));
      setLoading(false);
      return;
    }
    if (refillsLeft !== null && refillsLeft <= 0) {
      setMessage(t('refill_limit_reached'));
      setLoading(false);
      return;
    }
    if (totalXp < REFILL_PRICE) {
      setMessage(t('not_enough_gap'));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/shop/buy_energy_refill`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: telegramUserId }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        await fetchUserData();
        await fetchTotalSpent();

        if (typeof data.limit === 'number' && typeof data.refill_count === 'number') {
          const used = data.refill_count;
          setRefillLimit(data.limit);
          setRefillsLeft(Math.max(0, data.limit - used));
          setCurrentEnergy(data.energy);
        } else {
          await fetchRefillStatus();
        }

        setMessage(t('refill_success'));
      } else {
        setMessage(`${t('shop_error')}: ${data.message ?? ''}`);
      }
    } catch {
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  // derived
  const disableClickBoost =
    loading ||
    clickBoostLevel >= MAX_BOOST_LEVEL ||
    totalXp < clickBoostPrice ||
    (requiredInvites > 0 && invitesCount < requiredInvites);

  const disableEnergyUpgrade =
    loading ||
    totalXp < ENERGY_UPGRADE_PRICE ||
    (energyUpgradesLeft !== null && energyUpgradesLeft <= 0) ||
    (maxEnergyCap !== null && userMaxEnergy !== null && userMaxEnergy >= maxEnergyCap);

  const energyIsFull =
    currentEnergy !== null &&
    (refillMaxEnergy ?? userMaxEnergy ?? 0) > 0 &&
    currentEnergy >= (refillMaxEnergy ?? userMaxEnergy ?? 0);

  const disableRefill =
    loading ||
    totalXp < REFILL_PRICE ||
    (refillsLeft !== null && refillsLeft <= 0) ||
    energyIsFull;

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-4">🛒 {t('title_shop')}</h2>

      <p className="text-center text-sm text-[#7ee9ff] mb-6">
        💸 {t('total_spent')}: {totalSpent.toLocaleString()} $GAP
      </p>

      {/* Товар-футболка — ПЕРВЫМ */}
      <div className="bg-[#0e1a2b] border border-[#ffffff20] p-4 rounded-xl shadow-[0_0_10px_#ffffff20] text-center space-y-2 max-w-md mx-auto mb-6">
        <div className="relative w-fit mx-auto">
          <img
            src="/tshirt-preview-1.png"
            alt="T-shirt"
            className="w-24 h-24 mx-auto rounded-md object-cover"
          />
          <span className="absolute -right-2 -top-2 bg-[#00f0ff] text-[#0e1a2b] text-xs font-bold px-2 py-1 rounded-full shadow">
            {TSHIRT_LEFT}/{TSHIRT_TOTAL}
          </span>
        </div>

        <h3 className="text-lg font-semibold text-white/90">👕 Gappick T-shirt (Limited)</h3>
        <p className="text-sm text-[#999999]">Tezliklə satışda</p>

        <button
          disabled
          className="bg-[#cccccc20] text-[#cccccc] font-semibold px-4 py-2 rounded cursor-not-allowed"
        >
          {t('buy')}
        </button>
      </div>

      {/* Бустер на клики */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">💥 {t('boost_click')}</h3>
        <p className="text-sm text-[#a0f6ff]">
          {clickBoostPrice} $GAP ({t('level')}: x{clickBoostLevel + 1})
        </p>
        {requiredInvites > 0 && (
          <p className="text-xs text-[#89dfff]">
            {t('invited_friends')}: {invitesCount} • {t('boost_invites_required', { level: `x${nextBoostLevel}`, need: requiredInvites, have: invitesCount })}
          </p>
        )}

        <button
          onClick={handleBuyClickBoost}
          disabled={disableClickBoost}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>
        {clickBoostLevel >= MAX_BOOST_LEVEL && (
          <p className="text-xs text-[#ffadad] mt-1">{t('shop_max_level')}</p>
        )}
      </div>

      {/* Увеличение максимальной энергии */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">🔋 {t('energy_upgrade')}</h3>
        <p className="text-sm text-[#a0f6ff]">{ENERGY_UPGRADE_PRICE} $GAP</p>
        {energyUpgradeLimit !== null && energyUpgradesLeft !== null && (
          <p className="text-xs text-[#89dfff]">
            {t('available')}: {energyUpgradesLeft} / {energyUpgradeLimit}
          </p>
        )}
        {maxEnergyCap !== null && userMaxEnergy !== null && userMaxEnergy >= maxEnergyCap && (
          <p className="text-xs text-[#ffadad]">{t('max_energy_reached')}</p>
        )}

        <button
          onClick={handleBuyEnergyUpgrade}
          disabled={disableEnergyUpgrade}
          className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
        >
          {loading ? '...' : t('buy')}
        </button>
      </div>

      {/* Восполнение энергии */}
      <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
        <h3 className="text-lg font-semibold text-[#7ee9ff]">⚡ {t('refill_energy')}</h3>
        <p className="text-sm text-[#a0f6ff]">{REFILL_PRICE} $GAP</p>
        {refillLimit !== null && refillsLeft !== null && (
          <p className="text-xs text-[#89dfff]">
            {t('available')}: {refillsLeft} / {refillLimit}
          </p>
        )}
        {energyIsFull && <p className="text-xs text-[#ffadad]">{t('shop_restored')}</p>}

        <button
          onClick={handleRefillEnergy}
          disabled={disableRefill}
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










