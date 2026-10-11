/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        arabic: ['"Noto Sans Arabic"', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Calm professional palette per spec §5 UI/UX
        ink: { 50: '#f6f7f9', 100: '#eceef2', 900: '#0f172a', 950: '#020617' },
        accent: { 500: '#3b82f6', 600: '#2563eb' },
      },
    },
  },
  plugins: [],
};
