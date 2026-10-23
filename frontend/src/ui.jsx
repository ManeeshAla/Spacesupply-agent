import { X } from 'lucide-react'

export const STAGE_COLORS = { 1: '#22c55e', 2: '#3b82f6', 3: '#f59e0b', 4: '#94a3b8' }

export function Panel({ title, right, children, className = '', bodyClass = '' }) {
  return (
    <section className={`panel flex flex-col ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between px-4 pt-3 pb-2">
          <h3 className="panel-title">{title}</h3>
          {right}
        </header>
      )}
      <div className={`min-h-0 flex-1 px-4 pb-4 ${bodyClass}`}>{children}</div>
    </section>
  )
}

const TONES = {
  green: 'bg-ok/15 text-green-300 ring-1 ring-ok/30',
  blue: 'bg-accent/15 text-blue-300 ring-1 ring-accent/30',
  amber: 'bg-warn/15 text-amber-300 ring-1 ring-warn/30',
  red: 'bg-bad/15 text-red-300 ring-1 ring-bad/30',
  violet: 'bg-violet/15 text-violet-300 ring-1 ring-violet/30',
  slate: 'bg-slate-500/15 text-slate-300 ring-1 ring-slate-500/30',
  cyan: 'bg-cyan-400/10 text-cyan-300 ring-1 ring-cyan-400/30',
}
export const Badge = ({ tone = 'slate', children, className = '' }) => (
  <span className={`chip ${TONES[tone]} ${className}`}>{children}</span>
)

export const sevTone = (s) => ({ CRITICAL: 'red', WARNING: 'amber', INFO: 'blue' }[s] || 'slate')
export const statusTone = (s) =>
  ({
    INSTALLED: 'green', IN_WAREHOUSE: 'green', APPROVED: 'green', IN_ASSEMBLY_BAY: 'cyan',
    IN_INSPECTION: 'amber', INSPECTION_PENDING: 'amber', RECEIVED: 'amber',
    ORDERED: 'blue', REJECTED: 'red', COMPLETED: 'green', IN_PROGRESS: 'cyan', PENDING: 'slate',
    DELAYED: 'red', SUFFICIENT: 'green', LOW: 'amber', CRITICAL: 'red', ON_ORDER: 'blue', DONE: 'slate',
  }[s] || 'slate')
export const nice = (s = '') => s.replace(/_/g, ' ').toLowerCase().replace(/^\w/, (c) => c.toUpperCase())

export const sign = (h) => (h > 0 ? `+${h}h` : `${h}h`)

export function hourToDate(startIso, hour) {
  return new Date(new Date(startIso).getTime() + hour * 3600e3)
}
export const fmtDate = (d) => d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

export function Drawer({ open, onClose, title, children, width = 'max-w-xl' }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <aside className={`h-full w-full ${width} overflow-y-auto border-l border-line bg-space-800 p-5 shadow-2xl`} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          <button className="btn !px-2" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        {children}
      </aside>
    </div>
  )
}

export function Spinner({ label = 'Loading…' }) {
  return <div className="p-6 text-sm text-slate-400">{label}</div>
}

export function Bar({ value, color = '#3b82f6', className = '' }) {
  return (
    <div className={`h-1.5 w-full overflow-hidden rounded bg-space-600 ${className}`}>
      <div className="h-full rounded" style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </div>
  )
}

/** Render **bold** and keep line breaks. */
export function RichText({ text }) {
  return (
    <div className="whitespace-pre-line text-sm leading-relaxed">
      {text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
        p.startsWith('**') ? <strong key={i} className="text-white">{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>,
      )}
    </div>
  )
}
