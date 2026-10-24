/** @type {import('tailwindcss').Config} */
const rgb = (v) => `rgb(var(${v}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // role tokens (new, preferred going forward)
        plane: rgb('--plane'),
        surface: { 0: rgb('--surface-0'), 1: rgb('--surface-1'), 2: rgb('--surface-2'), 3: rgb('--surface-3'), 4: rgb('--surface-4'), DEFAULT: rgb('--surface-1') },
        hairline: rgb('--border'),
        ink: { DEFAULT: rgb('--ink'), 2: rgb('--ink-2'), 3: rgb('--ink-3'), muted: rgb('--ink-muted') },
        good: rgb('--good'),
        warning: rgb('--warning'),
        serious: rgb('--serious'),
        critical: rgb('--critical'),

        // legacy names remapped to the same role tokens, so existing markup re-themes.
        space: { 950: rgb('--plane'), 900: rgb('--surface-0'), 800: rgb('--surface-1'), 700: rgb('--surface-2'), 600: rgb('--surface-3'), 500: rgb('--surface-4') },
        line: rgb('--border'),
        accent: { DEFAULT: rgb('--accent'), soft: rgb('--accent-soft'), cyan: rgb('--aqua'), solid: rgb('--accent-solid'), ink: rgb('--accent-ink') },
        ok: rgb('--good'),
        warn: rgb('--warning'),
        bad: rgb('--critical'),
        violet: rgb('--violet'),
        // text greys (Tailwind slate) remapped to theme-aware ink roles
        slate: {
          100: rgb('--ink'), 200: rgb('--ink'), 300: rgb('--ink-2'),
          400: rgb('--ink-3'), 500: rgb('--ink-muted'), 600: rgb('--ink-muted'),
        },
        // status/brand hues as readable TEXT on tinted fills: text-t-good, text-t-critical ...
        t: { good: rgb('--t-good'), warning: rgb('--t-warning'), serious: rgb('--t-serious'), critical: rgb('--t-critical'),
             accent: rgb('--t-accent'), violet: rgb('--t-violet'), aqua: rgb('--t-aqua') },
        // stage identity (validated ordinal blue ramp)
        stage: { 1: rgb('--stage-1'), 2: rgb('--stage-2'), 3: rgb('--stage-3'), 4: rgb('--stage-4') },
      },
      fontFamily: {
        sans: ['Inter Variable', 'Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono Variable', 'JetBrains Mono', 'ui-monospace', 'SF Mono', 'Menlo', 'monospace'],
      },
      borderRadius: { xl: '0.75rem', lg: '0.5rem' },
      boxShadow: {
        sm: 'var(--shadow)',
        lg: 'var(--shadow-lg)',
        glow: 'var(--shadow)',  // legacy name -> ordinary shadow (no blue glow ring)
      },
      keyframes: {
        'fade-in': { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
        'slide-in': { '0%': { transform: 'translateX(12px)', opacity: 0 }, '100%': { transform: 'translateX(0)', opacity: 1 } },
        'drawer-in': { '0%': { transform: 'translateX(100%)' }, '100%': { transform: 'translateX(0)' } },
      },
      animation: {
        'fade-in': 'fade-in 0.15s ease-out',
        'slide-in': 'slide-in 0.18s ease-out',
        'drawer-in': 'drawer-in 0.2s cubic-bezier(0.16,1,0.3,1)',
      },
    },
  },
  plugins: [],
}
