import { createContext, useCallback, useContext, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, X } from 'lucide-react'
import { cx } from '../ui'

const ToastCtx = createContext(() => {})

/** `const toast = useToast(); toast({ title, body, tone: 'good'|'warn'|'bad'|'info' })` */
export const useToast = () => useContext(ToastCtx)

const STYLE = {
  good: [CheckCircle2, 'text-t-good'], warn: [AlertTriangle, 'text-t-warning'],
  bad: [OctagonAlert, 'text-t-critical'], info: [Info, 'text-t-accent'],
}

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const dismiss = useCallback((id) => setItems((x) => x.filter((i) => i.id !== id)), [])
  const push = useCallback((t) => {
    const id = Math.random().toString(36).slice(2)
    setItems((x) => [...x.slice(-3), { id, tone: 'info', ...t }])
    setTimeout(() => dismiss(id), t.duration ?? 5000)
  }, [dismiss])

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2" aria-live="polite">
        {items.map((t) => {
          const [Icon, color] = STYLE[t.tone] || STYLE.info
          return (
            <div key={t.id} role="status"
                 className="panel pointer-events-auto flex items-start gap-3 p-3 shadow-lg animate-slide-in">
              <Icon size={17} className={cx('mt-0.5 shrink-0', color)} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-ink">{t.title}</div>
                {t.body && <div className="mt-0.5 text-xs leading-relaxed text-ink-3">{t.body}</div>}
              </div>
              <button aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-ink-muted hover:text-ink"><X size={14} /></button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
