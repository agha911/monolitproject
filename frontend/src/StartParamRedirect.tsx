import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import MainScreen from './components/ui/MainScreen';
import WebApp from './telegram';

export default function StartParamRedirect() {
  const navigate = useNavigate();
  useEffect(() => {
    const parameter = WebApp.initDataUnsafe?.start_param;
    if (typeof parameter === 'string' && parameter.startsWith('pvp_')) {
      navigate('/pvp', { replace: true });
    }
  }, [navigate]);
  return <MainScreen />;
}
