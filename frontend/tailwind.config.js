/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      keyframes: {
        pulseNeon: {
          '0%, 100%': { boxShadow: '0 0 15px #00f0ff, 0 0 30px #00f0ff' },
          '50%': { boxShadow: '0 0 5px #00f0ff, 0 0 10px #00f0ff' },
        },
      },
      animation: {
        pulseNeon: 'pulseNeon 2s infinite ease-in-out',
      },
    },
  },
  plugins: [],
};