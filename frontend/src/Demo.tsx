import { useEffect, useRef, useState } from 'react';
import API_BASE_URL from './components/config';
import './demo.css';

type Progress = { energy: number; max_energy: number; total_xp: number; daily_progress: number; daily_reward_claimed: boolean; last_client_seq: number };
type Player = { id: number; username: string; total_xp: number };
type Session = { init_data: string; telegram_id: number; name: string };

export default function Demo() {
  const [session, setSession] = useState<Session | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Loading your playground…');
  const sequence = useRef(0);

  async function request<T>(path: string, auth: Session, body?: unknown): Promise<T> {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': auth.init_data },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please try again.');
    return data;
  }

  async function refresh(auth: Session) {
    const p = await request<Progress>('/api/game/progress', auth, { init_data: auth.init_data });
    sequence.current = Math.max(sequence.current, p.last_client_seq);
    setProgress(p);
    setPlayers(await request<Player[]>('/api/game/leaderboard', auth));
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/demo/session`);
        if (!res.ok) throw new Error('Start the demo server to open this playground.');
        const auth: Session = await res.json();
        if (cancelled) return;
        setSession(auth);
        await refresh(auth);
        setMessage('Try the game. Your first mission: collect 20 points.');
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : 'Demo server unavailable.');
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function act(action: 'click' | 'reward' | 'upgrade') {
    if (!session || busy) return;
    setBusy(true);
    try {
      if (action === 'click') {
        const result = await request<{ accepted_clicks: number }>('/api/game/clicks/flush', session, { init_data: session.init_data, delta_clicks: 10,
          client_seq: ++sequence.current, session_id: 'portfolio-demo' });
        setMessage(result.accepted_clicks > 0 ? `+${result.accepted_clicks} points. Keep exploring.` : 'Energy recharges over time. Take a short break.');
      } else if (action === 'reward') {
        const result = await request<{ status: string }>('/api/daily/claim_reward', session, { init_data: session.init_data });
        setMessage(result.status === 'reward_claimed' ? 'Mission complete! +50,000 points.' : 'Collect 20 points to unlock your reward.');
      } else {
        await request('/api/shop/buy_max_energy', session, { telegram_id: session.telegram_id });
        setMessage('Upgraded! Your energy capacity grew by 1,000.');
      }
      await refresh(session);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Please try again.');
    } finally { setBusy(false); }
  }

  return <div className="demo-shell">
    <header className="demo-header"><a className="demo-brand" href="/">MONOLIT<span>PLAY. CONNECT. GROW.</span></a><span className="demo-tag">Portfolio playground</span></header>
    <main className="demo-main">
      <section className="demo-intro"><div className="demo-eyebrow">A SMALL ACTION. A BIGGER WORLD.</div><h1>Make your<br/><em>next move.</em></h1><p>A social mini-game where every tap builds momentum.<br/>Explore the core experience with a fictional player.</p></section>
      <div className="demo-grid">
        <section className="demo-game demo-panel"><div className="demo-panel-top"><span>YOUR BALANCE</span><span className="demo-live">● Live playground</span></div><div className="demo-balance">{(progress?.total_xp ?? 0).toLocaleString()} <small>GAP</small></div><button className="demo-orb" aria-label="Collect 10 points" disabled={!progress || busy} onClick={() => act('click')}><span>M</span><small>TAP TO GROW · +10</small></button><div className="demo-energy"><span>Energy</span><strong>{progress?.energy ?? 0} / {progress?.max_energy ?? 1000}</strong></div><progress value={progress?.energy ?? 0} max={progress?.max_energy ?? 1000}/><p className="demo-status" role="status">{message}</p></section>
        <div className="demo-side"><section className="demo-panel"><div className="demo-eyebrow">01 / DAILY MISSION</div><h2>Start something good.</h2><p>Collect 20 points and unlock your first reward.</p><div className="demo-mission"><strong>{Math.min(progress?.daily_progress ?? 0, 20)} / 20</strong><span>+50,000 GAP</span></div><button className="demo-action" disabled={busy || !progress || (progress.daily_progress < 20) || progress.daily_reward_claimed} onClick={() => act('reward')}>{progress?.daily_reward_claimed ? 'Reward claimed ✓' : 'Claim reward →'}</button></section>
        <section className="demo-panel"><div className="demo-eyebrow">02 / POWER UP</div><h2>Room for more.</h2><p>Add 1,000 energy capacity to your next session.</p><button className="demo-action demo-secondary" disabled={busy || !progress || progress.total_xp < 2500} onClick={() => act('upgrade')}>Upgrade capacity <span>2,500 GAP</span></button></section></div>
      </div>
      <section className="demo-panel demo-leaderboard"><div><div className="demo-eyebrow">THE COMMUNITY</div><h2>A little friendly competition.</h2></div><ol>{players.map((player, index) => <li key={player.id}><span className="demo-rank">0{index+1}</span><span>{player.username.replace(/_/g, ' ')}</span><strong>{player.total_xp.toLocaleString()} <small>GAP</small></strong></li>)}</ol></section>
      <footer className="demo-footer">Demo players. Virtual points. No purchases or real rewards.<span>Built with React · FastAPI · PostgreSQL</span></footer>
    </main>
  </div>;
}
