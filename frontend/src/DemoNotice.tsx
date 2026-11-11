import { useEffect, useState } from 'react';

export default function DemoNotice() {
  const [notice, setNotice] = useState('Original game interface · Fictional player · Virtual points');
  useEffect(() => {
    const handleNotice = (event: Event) => setNotice((event as CustomEvent<string>).detail);
    window.addEventListener('demo-notice', handleNotice);
    return () => window.removeEventListener('demo-notice', handleNotice);
  }, []);
  return <aside className="demo-notice" role="status"><strong>DEMO</strong><span>{notice}</span></aside>;
}
