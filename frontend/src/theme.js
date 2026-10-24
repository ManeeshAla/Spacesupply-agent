import { useEffect, useState } from 'react'

const KEY = 'spacesupply-theme'

/** Current theme from the <html data-theme> the init script already set. */
export function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme)
  try { localStorage.setItem(KEY, theme) } catch { /* private mode */ }
}

/** Hook: [theme, toggle]. */
export function useTheme() {
  const [theme, setTheme] = useState(currentTheme)
  useEffect(() => { applyTheme(theme) }, [theme])
  return [theme, () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))]
}
