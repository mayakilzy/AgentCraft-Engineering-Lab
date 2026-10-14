/** @type {import('tailwindcss').Config} */
// AgentCraft Engineering Lab — Design System v1.0
// Tokens derived from approved_visual_reference.png + DESIGN_SPEC.md
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Cairo', 'system-ui', 'sans-serif'],
        arabic: ['Cairo', '"Noto Sans Arabic"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        brand: {
          50: '#eef5ff', 100: '#d9e8ff', 200: '#bcd7ff', 300: '#8ebcff',
          400: '#5895ff', 500: '#2b6def', 600: '#1764e9', 700: '#0f4dc0',
          800: '#103f9a', 900: '#123666',
        },
        navy: {
          50: '#f3f7fc', 100: '#e2ebf5', 400: '#2c4d77', 600: '#162f54',
          700: '#0e2746', 800: '#0a1d38', 900: '#061122',
        },
        grape: {
          50: '#f5f0ff', 100: '#ece0ff', 400: '#a982ec', 500: '#8557db', 600: '#6d3ec4',
        },
        success: {
          50: '#e2f8ee', 100: '#c5efdb', 500: '#139c61', 600: '#0f7a4c', 700: '#0c5e3a',
        },
        warn: {
          50: '#fff2dc', 100: '#ffe2b0', 500: '#d99324', 600: '#b47615', 700: '#8d5b0f',
        },
        danger: {
          50: '#fdecec', 100: '#fbd0d0', 500: '#dc2626', 600: '#b91c1c',
        },
        ink: {
          50: '#f6f7f9', 100: '#eceef2', 200: '#e2e8f0', 300: '#d6dde7',
          400: '#9aa7ba', 500: '#6c7b92', 600: '#53647c', 700: '#3a4a62',
          800: '#233f69', 900: '#172743', 950: '#0a1224',
        },
        surface: {
          DEFAULT: '#f4f7fc', card: '#ffffff', subtle: '#f8fafd',
          dark: '#0c1728', 'dark-card': '#15243a', 'dark-subtle': '#182d48',
        },
      },
      borderRadius: { card: '13px', chip: '20px', btn: '8px' },
      boxShadow: {
        card: '0 3px 14px #1c3c6910',
        'card-hover': '0 8px 24px #1c3c6924',
        focus: '0 0 0 3px #8ab7ff',
      },
      spacing: { sidebar: '252px' },
      maxWidth: { content: '1650px' },
      keyframes: {
        'fade-in': { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
      },
      animation: { 'fade-in': 'fade-in 0.25s cubic-bezier(0.4, 0, 0.2, 1)' },
    },
  },
  plugins: [],
};
