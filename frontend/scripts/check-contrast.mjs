// WCAG contrast check straight from the design tokens in src/index.css.
//   node scripts/check-contrast.mjs        (exit 1 if any required pair fails)
// Reads both themes, resolves each text/background pair, and reports the ratio.
// Tinted pills (Badge) are checked against their real composite: the status hue at the
// Badge's 15% alpha laid over the card surface.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')

function block(selector) {
  const start = css.indexOf(selector + ' {')
  const end = css.indexOf('\n}', start)
  const vars = {}
  for (const m of css.slice(start, end).matchAll(/--([\w-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;/g)) vars[m[1]] = [+m[2], +m[3], +m[4]]
  return vars
}
const dark = block(':root')
const light = { ...dark, ...block(':root[data-theme="light"]') }

const lin = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05) }
const over = (fg, bg, alpha) => fg.map((c, i) => Math.round(c * alpha + bg[i] * (1 - alpha)))

// [label, foreground token, background token or tint spec, minimum ratio]
const AA = 4.5   // normal text
const LARGE = 3  // large text / UI components
const checks = (t) => [
  ['body text on card', t.ink, t['surface-1'], AA],
  ['body text on page', t.ink, t.plane, AA],
  ['secondary text on card', t['ink-2'], t['surface-1'], AA],
  ['tertiary text on card', t['ink-3'], t['surface-1'], AA],
  ['tertiary text on page', t['ink-3'], t.plane, AA],
  ['muted text on card (captions, axis)', t['ink-muted'], t['surface-1'], LARGE],
  ['text on accent button', t['accent-ink'], t['accent-solid'], AA],
  ['accent text on card', t['t-accent'], t['surface-1'], AA],
  ['good text on card', t['t-good'], t['surface-1'], AA],
  ['warning text on card', t['t-warning'], t['surface-1'], AA],
  ['critical text on card', t['t-critical'], t['surface-1'], AA],
  ['violet text on card', t['t-violet'], t['surface-1'], AA],
  ['aqua text on card', t['t-aqua'], t['surface-1'], AA],
  ['good pill', t['t-good'], over(t.good, t['surface-1'], 0.15), AA],
  ['warning pill', t['t-warning'], over(t.warning, t['surface-1'], 0.15), AA],
  ['critical pill', t['t-critical'], over(t.critical, t['surface-1'], 0.15), AA],
  ['accent pill', t['t-accent'], over(t.accent, t['surface-1'], 0.15), AA],
  ['neutral pill', t['ink-2'], t['surface-3'], AA],
  ['Gantt label on stage 1 (dark ink)', [13, 13, 13], t['stage-1'], AA],
  ['Gantt label on stage 2 (dark ink)', [13, 13, 13], t['stage-2'], AA],
  ['Gantt label on stage 3 (white)', [255, 255, 255], t['stage-3'], AA],
  ['Gantt label on stage 4 (white)', [255, 255, 255], t['stage-4'], AA],
  ['stage 1 bar vs card (non-text)', t['stage-1'], t['surface-1'], 2],
  ['stage 4 bar vs card (non-text)', t['stage-4'], t['surface-1'], 2],
  ['hairline vs card (non-text)', t['border-strong'], t['surface-1'], 1.2],
]

let failed = 0
for (const [name, theme] of [['dark', dark], ['light', light]]) {
  console.log(`\n${name} theme`)
  for (const [label, fg, bg, min] of checks(theme)) {
    const r = ratio(fg, bg)
    const ok = r >= min
    if (!ok) failed += 1
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${r.toFixed(2).padStart(5)}:1  (need ${min})  ${label}`)
  }
}
console.log(failed ? `\n${failed} pair(s) below their minimum` : '\nall pairs pass')
process.exit(failed ? 1 : 0)
