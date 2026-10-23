/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        space: { 950: '#050a18', 900: '#070d1f', 800: '#0b1330', 700: '#101a3d', 600: '#16224d', 500: '#1f2f63' },
        line: '#1c2b5a',
        accent: { DEFAULT: '#3b82f6', soft: '#60a5fa', cyan: '#22d3ee' },
        ok: '#22c55e', warn: '#f59e0b', bad: '#ef4444', violet: '#a78bfa',
      },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'] },
      boxShadow: { glow: '0 0 0 1px rgba(59,130,246,.25), 0 8px 30px rgba(2,6,23,.6)' },
    },
  },
  plugins: [],
}
