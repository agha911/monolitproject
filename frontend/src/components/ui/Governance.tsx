// src/components/Governance.tsx
import React from 'react';

const Governance: React.FC = () => {
  return (
    <div className="w-full min-h-screen bg-[#0d1624] text-[#c9f6ff] px-4 pt-8 pb-28 flex flex-col items-center">
      {/* Header */}
      <div className="w-full max-w-xl text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#0e2238] border border-[#1f3b57] text-xs tracking-wide">
          <span className="w-2 h-2 rounded-full bg-[#00f0ff] animate-pulse" />
          Coming soon
        </div>
        <h1 className="mt-3 text-2xl font-bold text-[#7af9ff] drop-shadow-[0_0_8px_#00f0ff40]">
          DAO — birlikdə qərar vermək
        </h1>
        <p className="mt-2 text-sm text-[#9feaff]">
          DAO, fərdi yox, kollektiv qərarların üstünlüyünü ifadə edən bir yanaşmadır.
          Burada qaydalar şəffaf, nəticələr isə hamıya açıq olur.
        </p>
      </div>

      {/* Core cards */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-xl">
        <div className="p-4 rounded-2xl bg-[#0e2238] border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10]">
          <div className="text-[#7af9ff] font-semibold">Kollektiv güc</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Fərdlərin deyil, icmanın qərarları əsasdır. Hər kəsin səsi ümumi istiqaməti formalaşdırır.
          </p>
        </div>
        <div className="p-4 rounded-2xl bg-[#0e2238] border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10]">
          <div className="text-[#7af9ff] font-semibold">Şəffaflıq</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Qaydalar açıq şəkildə elan olunur və hər kəs nəticələri görə bilir.
          </p>
        </div>
        <div className="p-4 rounded-2xl bg-[#0e2238] border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10] sm:col-span-2">
          <div className="text-[#7af9ff] font-semibold">Yeni müsabiqə — tezliklə</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Qısa müddətdə start götürəcək xüsusi bir müsabiqə hazırlanır.
            Təfərrüatlar açıqlanmayıb, amma izləməyə dəyər.
          </p>
        </div>
      </div>

      {/* Coming soon actions */}
      <div className="mt-6 w-full max-w-xl">
        <div className="p-4 rounded-2xl bg-[#0e2238] border border-[#1f3b57]">
          <div className="text-sm text-[#9feaff]">
            İlk səsvermə: <span className="text-[#c9f6ff]">hazırlıq mərhələsi</span>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              disabled
              className="flex-1 px-4 py-2 rounded-xl bg-[#0d273d] border border-[#1f3b57] text-[#7aa1b7] opacity-60 cursor-not-allowed"
              title="Səsvermə tezliklə aktivləşəcək"
            >
              🗳️ Səs ver (tezliklə)
            </button>
            <a
              href="https://t.me/"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 rounded-xl bg-[#00f0ff] text-[#0b1a28] font-semibold shadow hover:shadow-[0_0_18px_#00f0ff40] transition"
            >
              🔔 Xəbərlər
            </a>
          </div>
        </div>
      </div>

      {/* FAQ-lite */}
      <div className="mt-6 w-full max-w-xl space-y-2">
        <details className="group rounded-2xl bg-[#0e2238] border border-[#1f3b57] p-4">
          <summary className="cursor-pointer select-none list-none flex items-center justify-between">
            <span className="text-[#7af9ff] font-medium">DAO nədir?</span>
            <span className="text-[#9feaff] group-open:rotate-180 transition">▾</span>
          </summary>
          <p className="mt-2 text-sm text-[#c9f6ffcc]">
            DAO — qaydaları kodlaşdırılmış və hamı tərəfindən qəbul olunan bir
            idarəetmə formasıdır. Qərarlar şəffaf şəkildə qəbul olunur.
          </p>
        </details>

        <details className="group rounded-2xl bg-[#0e2238] border border-[#1f3b57] p-4">
          <summary className="cursor-pointer select-none list-none flex items-center justify-between">
            <span className="text-[#7af9ff] font-medium">Səsvermə necə keçiriləcək?</span>
            <span className="text-[#9feaff] group-open:rotate-180 transition">▾</span>
          </summary>
          <p className="mt-2 text-sm text-[#c9f6ffcc]">
            İştirak qaydaları ayrıca elan ediləcək. Hər bir üzv öz payı qədər
            təsir gücünə sahib olacaq.
          </p>
        </details>
      </div>
    </div>
  );
};

export default Governance;
