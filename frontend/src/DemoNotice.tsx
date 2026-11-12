import { useEffect, useState } from 'react';

export default function DemoNotice() {
  const [notice, setNotice] = useState('Original game interface · Fictional player · Virtual points');
  const [expired, setExpired] = useState(false);
  useEffect(() => {
    const handleNotice = (event: Event) => setNotice((event as CustomEvent<string>).detail);
    window.addEventListener('demo-notice', handleNotice);
    const handleExpiry = () => { setExpired(true); setNotice('Your demo session expired. Reload to start fresh.'); };
    window.addEventListener('demo-expired', handleExpiry);
    return () => {
      window.removeEventListener('demo-notice', handleNotice);
      window.removeEventListener('demo-expired', handleExpiry);
    };
  }, []);
  return <aside className="demo-notice" role="status"><strong>DEMO</strong><span>{notice}</span>{expired && <button onClick={() => window.location.reload()}>Reload</button>}</aside>;
}
