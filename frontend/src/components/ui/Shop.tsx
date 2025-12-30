import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import API_BASE_URL from '../config';
import WebApp from '@twa-dev/sdk';

// дропы API
import { listDrops, buyDrop, type Drop, type Purchase } from '../scripts/api/drops';

const ENERGY_UPGRADE_PRICE = 2500;
const REFILL_PRICE = 2500;

// ⚠️ цена футболки (должна совпадать с backend TSHIRT_PRICE_GAP)
const TSHIRT_PRICE_GAP = 1000;

const INVITE_REQUIREMENTS: Record<number, number> = { 6: 1, 7: 5, 8: 10, 9: 15, 10: 20 };
const MAX_BOOST_LEVEL = 10;

// tshirt types (backend: /api/shop/tshirt/status)
type TshirtStatus = {
  drop_id: number;
  title: string;
  is_active: boolean;
  total_stock: number;
  sold_count: number;
  left: number;
  sale_started_at?: string | null;
  sold_out_at?: string | null;

  user_has_tshirt: boolean;
  user_size?: string | null;

  passive_is_active?: boolean | null;
  accrued_unclaimed?: number | null;
  cap_unclaimed?: number | null;
  rate_total?: number | null;
  cycle_seconds?: number | null;
  is_paused?: boolean | null;
};

const TSHIRT_SIZES = ['S', 'M', 'L', 'XL', 'XXL'] as const;
type TshirtSize = (typeof TSHIRT_SIZES)[number];

const Shop: React.FC = () => {
  const { t } = useTranslation();
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  // вкладки
  const [tab, setTab] = useState<'boosters' | 'drops'>('boosters');

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

  // tshirt status
  const [tshirtStatus, setTshirtStatus] = useState<TshirtStatus | null>(null);
  const [tshirtLoading, setTshirtLoading] = useState(false);
  const [tshirtModalOpen, setTshirtModalOpen] = useState(false);
  const [selectedTshirtSize, setSelectedTshirtSize] = useState<TshirtSize>('M');

  // дропы
  const [drops, setDrops] = useState<Drop[]>([]);
  const [dropsLoading, setDropsLoading] = useState(false);
  const [purchase, setPurchase] = useState<Purchase | null>(null);
  const [selectedDrop, setSelectedDrop] = useState<Drop | null>(null);

  const telegramUser = WebApp.initDataUnsafe?.user;
  const telegramUserId = telegramUser?.id;
  const initData = WebApp.initData;

  // loaders
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

  const fetchTshirtStatus = async () => {
    if (!telegramUserId) return;
    try {
      setTshirtLoading(true);
      const res = await fetch(
        `${API_BASE_URL}/api/shop/tshirt/status?telegram_id=${telegramUserId}`
      );
      if (!res.ok) {
        // не спамим ошибками: просто не показываем статус
        setTshirtStatus(null);
        return;
      }
      const data = await res.json();
      setTshirtStatus(data as TshirtStatus);
    } catch (err) {
      console.error('Ошибка при получении статуса футболки:', err);
      setTshirtStatus(null);
    } finally {
      setTshirtLoading(false);
    }
  };

  // дропы: загружаем при первом открытии вкладки
  useEffect(() => {
    const loadDropsOnce = async () => {
      if (tab !== 'drops' || drops.length > 0 || dropsLoading) return;
      try {
        setDropsLoading(true);
        const items = await listDrops();
        setDrops(items);
      } catch (e) {
        console.error('Ошибка загрузки дропов:', e);
      } finally {
        setDropsLoading(false);
      }
    };
    loadDropsOnce();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  // футболку подгружаем при открытии вкладки drops
  useEffect(() => {
    if (tab === 'drops') fetchTshirtStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  useEffect(() => {
    fetchUserData();
    fetchInvitesCount();
    fetchTotalSpent();
    fetchEnergyUpgradeStatus();
    fetchRefillStatus();
    // tshirt не тянем на старте, только на вкладке drops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // helpers
  const nextBoostLevel = Math.min(clickBoostLevel + 1, MAX_BOOST_LEVEL);
  const requiredInvites = INVITE_REQUIREMENTS[nextBoostLevel] ?? 0;
  const clickBoostPrice = 5000 * Math.pow(2, clickBoostLevel);

  // actions
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

  const handleBuyTshirt = async () => {
    if (!telegramUserId) return;
    if (!tshirtStatus) return;

    setLoading(true);
    setMessage('');

    if (!tshirtStatus.is_active) {
      setMessage('T-shirt drop inactive');
      setLoading(false);
      return;
    }
    if (tshirtStatus.left <= 0) {
      setMessage('Sold out');
      setLoading(false);
      return;
    }
    if (tshirtStatus.user_has_tshirt) {
      setMessage('Already purchased');
      setLoading(false);
      return;
    }
    if (totalXp < TSHIRT_PRICE_GAP) {
      setMessage(t('not_enough_gap'));
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/shop/tshirt/buy?telegram_id=${telegramUserId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ size: selectedTshirtSize }),
        }
      );

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail = data?.detail ?? 'buy_failed';
        setMessage(typeof detail === 'string' ? detail : 'buy_failed');
        return;
      }

      // успех
      setTshirtModalOpen(false);
      await fetchUserData();
      await fetchTotalSpent();
      await fetchTshirtStatus();
      setMessage(t('shop_success') || 'Success');
    } catch (err) {
      console.error('Ошибка покупки футболки:', err);
      setMessage(t('error'));
    } finally {
      setLoading(false);
    }
  };

  const handleClaimTshirt = async () => {
    if (!telegramUserId) return;

    setLoading(true);
    setMessage('');

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/shop/tshirt/claim?telegram_id=${telegramUserId}`,
        { method: 'POST' }
      );

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail = data?.detail ?? 'claim_failed';
        setMessage(typeof detail === 'string' ? detail : 'claim_failed');
        return;
      }

      // успех
      await fetchUserData();
      await fetchTshirtStatus();
      setMessage(t('shop_success') || 'Success');
    } catch (err) {
      console.error('Ошибка claim футболки:', err);
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
    loading || totalXp < REFILL_PRICE || (refillsLeft !== null && refillsLeft <= 0) || energyIsFull;

  const tshirtLeft = tshirtStatus?.left ?? 10;
  const tshirtTotal = tshirtStatus?.total_stock ?? 10;

  const tshirtAccrued = Number(tshirtStatus?.accrued_unclaimed ?? 0);
  const tshirtCap = Number(tshirtStatus?.cap_unclaimed ?? 50000);
  const tshirtPaused = Boolean(tshirtStatus?.is_paused ?? (tshirtAccrued >= tshirtCap));

  const disableTshirtBuy =
    loading ||
    tshirtLoading ||
    !telegramUserId ||
    !tshirtStatus ||
    !tshirtStatus.is_active ||
    tshirtStatus.left <= 0 ||
    tshirtStatus.user_has_tshirt ||
    totalXp < TSHIRT_PRICE_GAP;

  const disableTshirtClaim =
    loading || tshirtLoading || !telegramUserId || !tshirtStatus?.user_has_tshirt || tshirtAccrued <= 0;

  // tabs UI
  const Tabs = (
    <div className="max-w-md mx-auto mb-6">
      <div className="w-full bg-[#0e1a2b] border border-[#1f3b57] rounded-full p-1 flex">
        <button
          className={`flex-1 py-2 text-sm rounded-full transition ${
            tab === 'boosters' ? 'bg-[#00f0ff] text-[#0e1a2b] font-semibold' : 'text-[#7ee9ff]'
          }`}
          onClick={() => setTab('boosters')}
        >
          {t('shop_tab_boosters')}
        </button>
        <button
          className={`flex-1 py-2 text-sm rounded-full transition ${
            tab === 'drops' ? 'bg-[#00f0ff] text-[#0e1a2b] font-semibold' : 'text-[#7ee9ff]'
          }`}
          onClick={() => setTab('drops')}
        >
          {t('shop_tab_drops')}
        </button>
      </div>
    </div>
  );

  return (
    <div className="p-4 bg-[#131f2f] min-h-screen text-[#00f0ff]">
      <h2 className="text-xl font-bold text-center drop-shadow-md mb-4">🛒 {t('title_shop')}</h2>

      <p className="text-center text-sm text-[#7ee9ff] mb-6">
        💸 {t('total_spent')}: {totalSpent.toLocaleString()} $GAP
      </p>

      {Tabs}

      {/* === Вкладка БУСТЕРЫ === */}
      {tab === 'boosters' && (
        <>
          {/* Бустер на клики */}
          <div className="bg-[#0e1a2b] border border-[#00f0ff40] p-4 rounded-xl shadow-[0_0_10px_#00f0ff30] text-center space-y-2 max-w-md mx-auto mb-6">
            <h3 className="text-lg font-semibold text-[#7ee9ff]">💥 {t('boost_click')}</h3>
            <p className="text-sm text-[#a0f6ff]">
              {clickBoostPrice} $GAP ({t('level')}: x{clickBoostLevel + 1})
            </p>
            {requiredInvites > 0 && (
              <p className="text-xs text-[#89dfff]">
                {t('invited_friends')}: {invitesCount} •{' '}
                {t('boost_invites_required', {
                  level: `x${nextBoostLevel}`,
                  need: requiredInvites,
                  have: invitesCount,
                })}
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
        </>
      )}

      {/* === Вкладка ДРОПЫ === */}
      {tab === 'drops' && (
        <div className="max-w-md mx-auto">
          {/* Футболка (реальная логика) */}
          <div className="bg-[#0e1a2b] border border-[#ffffff20] p-4 rounded-xl shadow-[0_0_10px_#ffffff20] text-center space-y-2 mb-6">
            <div className="relative w-fit mx-auto">
              <img
                src="/tshirt-preview-1.png"
                alt="T-shirt"
                className="w-24 h-24 mx-auto rounded-md object-cover"
              />
              <span className="absolute -right-2 -top-2 bg-[#00f0ff] text-[#0e1a2b] text-xs font-bold px-2 py-1 rounded-full shadow">
                {tshirtLeft}/{tshirtTotal}
              </span>
            </div>

            {!tshirtStatus && (
              <>
                <h3 className="text-lg font-semibold text-white/90">👕 Gappick T-shirt (Limited)</h3>
                <p className="text-sm text-[#999999]">
                  {tshirtLoading ? (t('common.loading') || 'Loading...') : '—'}
                </p>
                <button
                  disabled
                  className="bg-[#cccccc20] text-[#cccccc] font-semibold px-4 py-2 rounded cursor-not-allowed"
                >
                  {t('buy')}
                </button>
              </>
            )}

            {tshirtStatus && !tshirtStatus.user_has_tshirt && (
              <>
                <h3 className="text-lg font-semibold text-white/90">👕 {tshirtStatus.title}</h3>
                <p className="text-sm text-[#a0f6ff]">{TSHIRT_PRICE_GAP.toLocaleString()} $GAP</p>

                {!tshirtStatus.is_active && (
                  <p className="text-xs text-[#ffadad]">Drop inactive</p>
                )}
                {tshirtStatus.left <= 0 && <p className="text-xs text-[#ffadad]">Sold out</p>}

                <button
                  onClick={() => setTshirtModalOpen(true)}
                  disabled={disableTshirtBuy}
                  className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40"
                >
                  {loading ? '...' : t('buy')}
                </button>

                {totalXp < TSHIRT_PRICE_GAP && (
                  <p className="text-xs text-[#ffadad]">{t('not_enough_gap')}</p>
                )}
              </>
            )}

            {tshirtStatus && tshirtStatus.user_has_tshirt && (
              <>
                <h3 className="text-lg font-semibold text-white/90">💰 $GAP Farm (T-shirt)</h3>
                <p className="text-xs text-[#89dfff]">
                  {t('level')}: {tshirtStatus.user_size ? `Size ${tshirtStatus.user_size}` : '—'}
                </p>

                <div className="mt-2 text-sm text-[#a0f6ff]">
                  {tshirtAccrued.toLocaleString()} / {tshirtCap.toLocaleString()} $GAP
                </div>

                <div className="w-full bg-[#ffffff10] rounded-full h-2 mt-2 overflow-hidden">
                  <div
                    className="h-2 bg-[#00f0ff]"
                    style={{
                      width: `${Math.min(100, Math.round((tshirtAccrued / Math.max(1, tshirtCap)) * 100))}%`,
                    }}
                  />
                </div>

                {tshirtPaused && (
                  <p className="text-xs text-[#ffadad] mt-2">
                    Pause: cap reached. Claim to continue.
                  </p>
                )}

                <button
                  onClick={handleClaimTshirt}
                  disabled={disableTshirtClaim}
                  className="bg-[#00f0ff] text-[#0e1a2b] font-semibold px-4 py-2 rounded hover:scale-105 transition-all disabled:opacity-40 mt-3"
                >
                  {loading ? '...' : 'Claim'}
                </button>
              </>
            )}
          </div>

          {/* Модалка выбора размера */}
          {tshirtModalOpen && (
            <div
              // ✅ поднимаем sheet над нижней навигацией + учитываем safe-area
              className="fixed inset-0 bg-black/50 flex items-end pb-[calc(env(safe-area-inset-bottom)+96px)]"
              onClick={(e) => {
                if (e.target === e.currentTarget) setTshirtModalOpen(false);
              }}
            >
              <div
                // ✅ небольшой дополнительный отступ + padding снизу на всякий случай
                className="w-full rounded-t-2xl bg-white p-4 pb-[calc(env(safe-area-inset-bottom)+24px)] relative mb-2"
              >
                <button
                  className="absolute right-3 top-3 w-8 h-8 rounded-full bg-black/80 text-white flex items-center justify-center"
                  onClick={() => setTshirtModalOpen(false)}
                  aria-label={t('actions.close') || 'Close'}
                  title={t('actions.close') || 'Close'}
                >
                  ×
                </button>

                <div className="font-semibold mb-2">Select size</div>

                <div className="flex flex-wrap gap-2">
                  {TSHIRT_SIZES.map((s) => (
                    <button
                      key={s}
                      className={`px-3 py-2 rounded-lg border text-sm font-semibold ${
                        selectedTshirtSize === s
                          ? 'bg-black text-white border-black'
                          : 'bg-white text-black border-gray-300'
                      }`}
                      onClick={() => setSelectedTshirtSize(s)}
                      type="button"
                    >
                      {s}
                    </button>
                  ))}
                </div>

                <div className="mt-3 text-sm">
                  Price: <b>{TSHIRT_PRICE_GAP.toLocaleString()} $GAP</b>
                </div>

                <button
                  className="mt-4 w-full px-4 py-3 rounded-xl bg-black text-white font-semibold disabled:opacity-50"
                  onClick={handleBuyTshirt}
                  disabled={disableTshirtBuy}
                >
                  {loading ? '...' : 'Buy'}
                </button>

                {tshirtStatus?.left != null && (
                  <div className="mt-2 text-xs opacity-70">
                    Left: {tshirtStatus.left}/{tshirtStatus.total_stock}
                  </div>
                )}
              </div>
            </div>
          )}

          {dropsLoading && (
            <div className="text-center text-sm text-[#7ee9ff] mb-4">{t('common.loading')}</div>
          )}
          {!dropsLoading && drops.length === 0 && (
            <div className="text-center text-sm text-[#7ee9ff] mb-4">
              {t('drops_empty') || 'Нет активных дропов'}
            </div>
          )}

          <div className="space-y-3">
            {drops.map((d) => {
              const userOut = (d as any).user_remaining === 0;
              const leftAll = (d as any).remaining;
              const leftUser = (d as any).user_remaining;

              return (
                <div
                  key={d.id}
                  className={`rounded-2xl p-4 bg-[#0e1a2b] border ${
                    userOut ? 'border-[#ffffff30]' : 'border-[#00f0ff40]'
                  } text-white flex items-center justify-between`}
                >
                  <div>
                    <div className="text-base font-semibold">{d.title}</div>
                    <div className="text-xs opacity-80">
                      {t('drop_discount', { percent: d.discount_percent })} ·{' '}
                      {t('drop_price', { price: d.price_coins })}
                    </div>

                    {(leftAll != null || leftUser != null) && (
                      <div className="text-[11px] opacity-70 mt-1">
                        {leftAll != null && <span>{t('available')}: {leftAll}</span>}
                        {leftAll != null && leftUser != null && <span> • </span>}
                        {leftUser != null && (
                          <span>{t('your_available') ?? 'You'}: {leftUser}</span>
                        )}
                      </div>
                    )}
                  </div>

                  {userOut ? (
                    <span className="px-3 py-1 rounded-lg bg-[#cccccc20] text-[#cccccc] text-sm font-semibold">
                      ✓
                    </span>
                  ) : (
                    <button
                      className="px-3 py-1 rounded-lg bg-[#00f0ff] text-[#0e1a2b] text-sm font-semibold"
                      onClick={async () => {
                        try {
                          setSelectedDrop(d);
                          const p = await buyDrop(d.id);
                          setPurchase(p);
                          await fetchUserData();
                          await fetchTotalSpent();
                          // локально уменьшим user_remaining, если фронту вернули лимиты
                          if (leftUser != null) {
                            (d as any).user_remaining = Math.max(0, leftUser - 1);
                            setDrops((prev) =>
                              prev.map((x) => (x.id === d.id ? { ...x, ...(d as any) } : x))
                            );
                          }
                        } catch (e: any) {
                          alert(e?.message || t('shop_error'));
                        }
                      }}
                    >
                      {t('buy')}
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Модалка результата покупки дропа */}
          {purchase && (
            <div
              className="fixed inset-0 bg-black/50 flex items-end"
              onClick={(e) => {
                if (e.target === e.currentTarget) {
                  setPurchase(null);
                  setSelectedDrop(null);
                }
              }}
            >
              <div className="w-full rounded-t-2xl bg-white p-4 relative">
                {/* крестик */}
                <button
                  className="absolute right-3 top-3 w-8 h-8 rounded-full bg-black/80 text-white flex items-center justify-center"
                  onClick={() => {
                    setPurchase(null);
                    setSelectedDrop(null);
                  }}
                  aria-label={t('actions.close') || 'Close'}
                  title={t('actions.close') || 'Close'}
                >
                  ×
                </button>

                <div className="font-semibold mb-1">{t('drop_code_title') || 'Код дропа'}</div>
                <div className="text-sm">
                  {t('drop_code_hint') || 'Покажите этот код партнёру:'}{' '}
                  <b>{purchase.unique_code}</b>
                </div>

                <div className="text-xs opacity-70 mt-2">
                  {(purchase.partner_name || (selectedDrop as any)?.partner?.name) ?? '—'} ·{' '}
                  {(purchase.discount_percent ??
                    (selectedDrop as any)?.discount_percent ??
                    '-') + '%'}
                </div>
                <div className="text-xs opacity-70 mt-1">
                  {t('drop_price', {
                    price: (selectedDrop as any)?.price_coins ?? purchase.price_coins ?? 0,
                  })}
                </div>

                <div className="mt-3 flex gap-2">
                  <button
                    className="px-3 py-2 rounded-lg bg-black text-white"
                    onClick={async () => {
                      await navigator.clipboard.writeText(purchase.unique_code);
                      alert(t('alerts.copied') || 'ID скопирован');
                    }}
                  >
                    {t('actions.copy') || 'Копировать'}
                  </button>
                  <button
                    className="px-3 py-2 rounded-lg bg-gray-200"
                    onClick={() => {
                      setPurchase(null);
                      setSelectedDrop(null);
                    }}
                  >
                    {t('actions.close') || 'Закрыть'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {message && <p className="text-sm mt-4 text-center text-[#a0f6ff]">{message}</p>}
    </div>
  );
};

export default Shop;













