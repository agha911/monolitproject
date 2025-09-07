// src/components/Governance.tsx
import React from 'react';

const Governance: React.FC = () => {
  return (
    <div className="relative w-full min-h-screen bg-[#0d1624] text-[#c9f6ff] px-4 pt-8 pb-28 flex flex-col items-center overflow-hidden">
      {/* ==== Animated Background Layers ==== */}
      {/* radial blobs */}
      <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-20 -left-24 w-80 h-80 rounded-full opacity-[0.18] blur-3xl bg-[conic-gradient(at_top_right,_#00f0ff_0%,_#7af9ff_25%,_transparent_60%)] animate-blob-slow" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 rounded-full opacity-[0.14] blur-3xl bg-[conic-gradient(at_bottom_left,_#00f0ff_0%,_#7af9ff_30%,_transparent_70%)] animate-blob-slower" />
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[36rem] h-[36rem] rounded-full opacity-[0.08] blur-[90px] bg-[radial-gradient(circle,_#00f0ff33,_transparent_60%)] animate-blob-very-slow" />
      </div>

      {/* animated grid */}
      <div className="pointer-events-none absolute inset-0 -z-10 opacity-[0.12]">
        <div className="absolute inset-0 bg-[linear-gradient(#1a2a40_1px,transparent_1px),linear-gradient(90deg,#1a2a40_1px,transparent_1px)] bg-[size:40px_40px] animate-grid-shift" />
      </div>

      {/* fireflies */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        {[...Array(10)].map((_, i) => (
          <span
            key={i}
            className="absolute w-1.5 h-1.5 rounded-full bg-[#7af9ff] opacity-70 animate-firefly"
            style={{
              top: `${Math.random() * 100}%`,
              left: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 6}s`,
              animationDuration: `${6 + Math.random() * 6}s`,
              filter: 'drop-shadow(0 0 6px #00f0ff)',
            }}
          />
        ))}
      </div>

      {/* Header */}
      <div className="w-full max-w-xl text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#0e2238cc] border border-[#1f3b57] text-xs tracking-wide backdrop-blur-[2px]">
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
        <div className="p-4 rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10] backdrop-blur-[2px]">
          <div className="text-[#7af9ff] font-semibold">Kollektiv güc</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Fərdlərin deyil, icmanın qərarları əsasdır. Hər kəsin səsi ümumi istiqaməti formalaşdırır.
          </p>
        </div>
        <div className="p-4 rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10] backdrop-blur-[2px]">
          <div className="text-[#7af9ff] font-semibold">Şəffaflıq</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Qaydalar açıq şəkildə elan olunur və hər kəs nəticələri görə bilir.
          </p>
        </div>
        <div className="p-4 rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] shadow-[0_0_16px_#00f0ff10] backdrop-blur-[2px] sm:col-span-2">
          <div className="text-[#7af9ff] font-semibold">Yeni müsabiqə — tezliklə</div>
          <p className="mt-1 text-sm text-[#c9f6ffcc]">
            Qısa müddətdə start götürəcək xüsusi bir müsabiqə hazırlanır.
            Təfərrüatlar açıqlanmayıb, amma izləməyə dəyər.
          </p>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-xs px-2 py-1 rounded-lg bg-[#10263d] border border-[#1f3b57]">#teaser</span>
            <span className="text-xs px-2 py-1 rounded-lg bg-[#10263d] border border-[#1f3b57]">#community</span>
          </div>
        </div>
      </div>

      {/* Coming soon actions */}
      <div className="mt-6 w-full max-w-xl">
        <div className="p-4 rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] backdrop-blur-[2px]">
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
          </div>
        </div>
      </div>

      {/* FAQ-lite */}
      <div className="mt-6 w-full max-w-xl space-y-2">
        <details className="group rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] p-4 backdrop-blur-[2px]">
          <summary className="cursor-pointer select-none list-none flex items-center justify-between">
            <span className="text-[#7af9ff] font-medium">DAO nədir?</span>
            <span className="text-[#9feaff] group-open:rotate-180 transition">▾</span>
          </summary>
          <p className="mt-2 text-sm text-[#c9f6ffcc]">
            DAO — qaydaları kodlaşdırılmış və hamı tərəfindən qəbul olunan bir idarəetmə formasıdır.
            Qərarlar şəffaf şəkildə qəbul olunur.
          </p>
        </details>

        <details className="group rounded-2xl bg-[#0e2238]/90 border border-[#1f3b57] p-4 backdrop-blur-[2px]">
          <summary className="cursor-pointer select-none list-none flex items-center justify-between">
            <span className="text-[#7af9ff] font-medium">Səsvermə necə keçiriləcək?</span>
            <span className="text-[#9feaff] group-open:rotate-180 transition">▾</span>
          </summary>
          <p className="mt-2 text-sm text-[#c9f6ffcc]">
            İştirak qaydaları ayrıca elan ediləcək. Hər bir üzv öz payı qədər təsir gücünə sahib olacaq.
          </p>
        </details>
      </div>

      {/* Inline keyframes for animations */}
      <style>{`
        @keyframes blob-slow {
          0% { transform: translate(0,0) scale(1); }
          50% { transform: translate(20px, -10px) scale(1.05); }
          100% { transform: translate(0,0) scale(1); }
        }
        @keyframes blob-slower {
          0% { transform: translate(0,0) scale(1); }
          50% { transform: translate(-25px, 15px) scale(1.08); }
          100% { transform: translate(0,0) scale(1); }
        }
        @keyframes blob-very-slow {
          0% { transform: translate(-10px, 10px) scale(1); }
          50% { transform: translate(15px, -15px) scale(1.04); }
          100% { transform: translate(-10px, 10px) scale(1); }
        }
        .animate-blob-slow { animation: blob-slow 18s ease-in-out infinite; }
        .animate-blob-slower { animation: blob-slower 26s ease-in-out infinite; }
        .animate-blob-very-slow { animation: blob-very-slow 36s ease-in-out infinite; }

        @keyframes grid-shift {
          0% { background-position: 0 0, 0 0; }
          100% { background-position: 40px 40px, 40px 40px; }
        }
        .animate-grid-shift { animation: grid-shift 20s linear infinite; }

        @keyframes firefly {
          0%   { transform: translate(0,0); opacity: .7; }
          25%  { transform: translate(10px,-6px); opacity: .9; }
          50%  { transform: translate(-6px,8px); opacity: .65; }
          75%  { transform: translate(8px,4px); opacity: .85; }
          100% { transform: translate(0,0); opacity: .7; }
        }
        .animate-firefly { animation: firefly 8s ease-in-out infinite; }
      `}</style>
    </div>
  );
};

export default Governance;
