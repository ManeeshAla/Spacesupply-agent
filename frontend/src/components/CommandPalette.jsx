import { useEffect, useMemo, useRef, useState } from 'react'
import { CornerDownLeft, Search, Sparkles } from 'lucide-react'
import { cx } from '../ui'

/**
 * ⌘K / Ctrl+K palette. `items` = [{ id, group, label, hint, icon, run }]. Typing filters them, and
 * whatever you typed can always be sent to the assistant as a question.
 */
export default function CommandPalette({ open, onClose, items, onAsk }) {
  const [q, setQ] = useState('')
  const [idx, setIdx] = useState(0)
  const input = useRef(null)

  useEffect(() => { if (open) { setQ(''); setIdx(0); setTimeout(() => input.current?.focus(), 10) } }, [open])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const hit = needle ? items.filter((i) => `${i.label} ${i.hint || ''} ${i.group}`.toLowerCase().includes(needle)) : items
    const out = [...hit]
    if (needle) out.push({ id: 'ask', group: 'Assistant', label: `Ask the assistant: “${q.trim()}”`, icon: Sparkles, run: () => onAsk(q.trim()) })
    return out
  }, [q, items, onAsk])

  useEffect(() => { setIdx(0) }, [q])
  if (!open) return null

  const run = (r) => { onClose(); r?.run() }
  const onKey = (e) => {
    if (e.key === 'Escape') onClose()
    else if (e.key === 'ArrowDown') { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); run(results[idx]) }
  }

  let lastGroup = null
  return (
    <div className="fixed inset-0 z-[70] flex items-start justify-center bg-black/50 px-4 pt-[14vh] backdrop-blur-[2px] animate-fade-in" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKey} onClick={(e) => e.stopPropagation()}
           className="panel w-full max-w-xl overflow-hidden shadow-lg">
        <div className="flex items-center gap-2.5 border-b border-hairline px-4">
          <Search size={16} className="text-ink-muted" />
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Go to a page, run an action, or ask a question…"
                 className="h-12 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted" />
          <kbd className="rounded border border-hairline px-1.5 py-0.5 text-[10px] text-ink-muted">Esc</kbd>
        </div>
        <ul className="max-h-[50vh] overflow-y-auto p-1.5">
          {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-ink-3">No matches</li>}
          {results.map((r, i) => {
            const head = r.group !== lastGroup ? (lastGroup = r.group) : null
            const Icon = r.icon
            return (
              <li key={r.id}>
                {head && <div className="eyebrow px-3 pb-1 pt-2.5">{head}</div>}
                <button onClick={() => run(r)} onMouseEnter={() => setIdx(i)}
                        className={cx('flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-[13px] transition-colors',
                          i === idx ? 'bg-surface-2 text-ink' : 'text-ink-2')}>
                  {Icon && <Icon size={15} className={i === idx ? 'text-t-accent' : 'text-ink-muted'} />}
                  <span className="flex-1 truncate">{r.label}</span>
                  {r.hint && <span className="text-xs text-ink-muted">{r.hint}</span>}
                  {i === idx && <CornerDownLeft size={13} className="text-ink-muted" />}
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
