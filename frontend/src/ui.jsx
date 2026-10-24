import { useEffect, useRef } from 'react'
import { ChevronDown, Inbox, Search, X } from 'lucide-react'

export const cx = (...a) => a.filter(Boolean).join(' ')

/* Stage identity: a validated single-hue ORDINAL ramp (Stage 1 lightest -> Stage 4 darkest).
   Stages are a sequence, so one ramp reads correctly and never collides with status colours. */
export const STAGE_COLORS = {
  1: 'rgb(var(--stage-1))', 2: 'rgb(var(--stage-2))', 3: 'rgb(var(--stage-3))', 4: 'rgb(var(--stage-4))',
}

/* ---------------------------------------------------------------- surfaces */
export function Panel({ title, subtitle, right, children, className = '', bodyClass = '', flush = false, height, ...rest }) {
  return (
    <section className={cx('panel flex flex-col', className)} {...rest}>
      {(title || right) && (
        <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 pb-1 pt-3.5">
          <div className="min-w-0">
            {title && <h3 className="panel-title truncate">{title}</h3>}
            {subtitle && <p className="mt-0.5 truncate text-xs text-ink-3">{subtitle}</p>}
          </div>
          {right && <div className="flex flex-wrap items-center gap-2">{right}</div>}
        </header>
      )}
      {/* `height` pins the body (feeds that must scroll inside the card); otherwise it grows with content */}
      <div className={cx('min-h-0', height ? 'shrink-0 overflow-hidden' : 'flex-1', flush ? '' : 'px-4 pb-4 pt-2', bodyClass)}
           style={height ? { height } : undefined}>{children}</div>
    </section>
  )
}

/** Page header: title, one-line description, actions. */
export function PageHeader({ title, description, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-[22px] font-semibold leading-tight tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-[13px] text-ink-3">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/* ---------------------------------------------------------------- status */
const TONES = {
  green: 'bg-good/15 text-t-good', blue: 'bg-accent/15 text-t-accent', amber: 'bg-warning/15 text-t-warning',
  red: 'bg-critical/15 text-t-critical', violet: 'bg-violet/15 text-t-violet', cyan: 'bg-accent-cyan/15 text-t-aqua',
  slate: 'bg-surface-3 text-ink-2',
}
const DOTS = {
  green: 'bg-good', blue: 'bg-accent', amber: 'bg-warning', red: 'bg-critical', violet: 'bg-violet', cyan: 'bg-accent-cyan', slate: 'bg-ink-muted',
}

/** A quiet pill: tinted fill + readable text. Use for genuine status/category only. */
export const Badge = ({ tone = 'slate', children, className = '', dot = false }) => (
  <span className={cx('chip', TONES[tone] || TONES.slate, className)}>
    {dot && <span className={cx('h-1.5 w-1.5 rounded-full', DOTS[tone] || DOTS.slate)} />}
    {children}
  </span>
)

/** Dot + text. Lighter than a pill, for tables with many statuses. */
export const StatusDot = ({ tone = 'slate', children, className = '' }) => (
  <span className={cx('inline-flex items-center gap-1.5 text-[13px] text-ink-2', className)}>
    <span className={cx('h-2 w-2 shrink-0 rounded-full', DOTS[tone] || DOTS.slate)} />{children}
  </span>
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

/* ---------------------------------------------------------------- controls */
export function Button({ variant = 'secondary', size = 'md', icon: Icon, children, className = '', ...rest }) {
  const v = { primary: 'btn-primary', danger: 'btn-danger', ghost: 'btn-ghost', secondary: '' }[variant]
  return (
    <button className={cx('btn', v, size === 'sm' && '!px-2.5 !py-1 !text-xs', className)} {...rest}>
      {Icon && <Icon size={size === 'sm' ? 13 : 15} />}{children}
    </button>
  )
}

export function IconButton({ label, children, className = '', ...rest }) {
  return (
    <button aria-label={label} title={label}
            className={cx('inline-flex h-8 w-8 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink', className)}
            {...rest}>{children}</button>
  )
}

/** Native select (keeps keyboard + mobile behaviour) with a custom chevron. */
export function Select({ value, onChange, options, className = '', label, ...rest }) {
  return (
    <label className={cx('relative inline-flex items-center', className)}>
      {label && <span className="sr-only">{label}</span>}
      <select className="input w-full cursor-pointer appearance-none pr-8" value={value}
              onChange={(e) => onChange(e.target.value)} {...rest}>
        {options.map((o) => {
          const opt = typeof o === 'object' ? o : { value: o, label: o }
          return <option key={opt.value} value={opt.value}>{opt.label}</option>
        })}
      </select>
      <ChevronDown size={14} className="pointer-events-none absolute right-2.5 text-ink-muted" />
    </label>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', className = '' }) {
  return (
    <label className={cx('relative inline-flex items-center', className)}>
      <Search size={14} className="pointer-events-none absolute left-3 text-ink-muted" />
      <input className="input w-full !pl-8" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}

/** Segmented control: a small set of mutually exclusive options. */
export function Segmented({ value, onChange, options, className = '', size = 'md' }) {
  return (
    <div role="tablist" className={cx('inline-flex rounded-lg border border-hairline bg-surface-0 p-0.5', className)}>
      {options.map((o) => {
        const opt = typeof o === 'object' ? o : { value: o, label: o }
        const on = opt.value === value
        return (
          <button key={opt.value} role="tab" aria-selected={on} onClick={() => onChange(opt.value)}
                  className={cx('rounded-md font-medium transition-colors', size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-[13px]',
                    on ? 'bg-surface-1 text-ink shadow-sm ring-1 ring-hairline' : 'text-ink-3 hover:text-ink')}>
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

/* ---------------------------------------------------------------- data display */
/** Headline metric: label, big figure, supporting line, optional right-hand slot. */
export function StatCard({ label, value, sub, tone, icon: Icon, onClick, children, className = '' }) {
  const color = { good: 'text-t-good', warn: 'text-t-warning', bad: 'text-t-critical' }[tone] || 'text-ink'
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag onClick={onClick}
         className={cx('panel p-4 text-left', onClick && 'cursor-pointer transition-colors hover:bg-surface-2', className)}>
      <div className="flex items-center justify-between">
        <span className="text-[13px] text-ink-3">{label}</span>
        {Icon && <Icon size={15} className="text-ink-muted" />}
      </div>
      <div className={cx('mt-1.5 text-[28px] font-semibold leading-none tracking-tight tabular', color)}>{value}</div>
      {sub && <div className="mt-1.5 text-xs text-ink-3">{sub}</div>}
      {children}
    </Tag>
  )
}

export function Bar({ value, color = 'rgb(var(--accent))', className = '', height = 6 }) {
  return (
    <div className={cx('w-full overflow-hidden rounded-full bg-surface-3', className)} style={{ height }}>
      <div className="h-full rounded-full transition-all" style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </div>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={cx('animate-pulse rounded-md bg-surface-3/70', className)} />
}

/** Loading placeholder shaped like content rather than the word "Loading…". */
export function Spinner({ label = 'Loading…' }) {
  return (
    <div className="space-y-3 p-2" role="status" aria-label={label}>
      <Skeleton className="h-6 w-48" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
      <Skeleton className="h-64" />
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, body, action }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-ink-muted"><Icon size={18} /></div>
      <div className="text-sm font-medium text-ink">{title}</div>
      {body && <p className="max-w-sm text-[13px] text-ink-3">{body}</p>}
      {action}
    </div>
  )
}

/** Consistent table: sticky header, hover rows, optional click. */
export function DataTable({ columns, rows, rowKey, onRowClick, empty, maxHeight, dense = false }) {
  return (
    <div className="overflow-auto rounded-lg border border-hairline" style={maxHeight ? { maxHeight } : undefined}>
      <table className="w-full">
        <thead className="sticky top-0 z-10 bg-surface-0">
          <tr>{columns.map((c) => <th key={c.key} className={cx('th', c.align === 'right' && 'text-right', c.className)}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={columns.length}>{empty || <EmptyState title="Nothing to show" />}</td></tr>}
          {rows.map((r, i) => (
            <tr key={rowKey ? rowKey(r) : i} onClick={onRowClick ? () => onRowClick(r) : undefined}
                className={cx('border-t border-hairline transition-colors hover:bg-surface-2', onRowClick && 'cursor-pointer')}>
              {columns.map((c) => (
                <td key={c.key} className={cx('td', dense && '!py-1.5', c.align === 'right' && 'text-right', c.className)}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---------------------------------------------------------------- overlays */
export function Drawer({ open, onClose, title, subtitle, children, width = 'max-w-xl' }) {
  const ref = useRef(null)
  const prev = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    prev.current = document.activeElement
    ref.current?.focus()
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); prev.current?.focus?.() }
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[2px] animate-fade-in" onClick={onClose}>
      <aside ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : undefined}
             className={cx('h-full w-full overflow-y-auto border-l border-hairline bg-surface-1 shadow-lg outline-none animate-drawer-in', width)}
             onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-hairline bg-surface-1/95 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold tracking-tight text-ink">{title}</h2>
            {subtitle && <p className="mt-0.5 text-[13px] text-ink-3">{subtitle}</p>}
          </div>
          <IconButton label="Close" onClick={onClose}><X size={16} /></IconButton>
        </div>
        <div className="p-5">{children}</div>
      </aside>
    </div>
  )
}

/** **bold**, `- ` bullets and line breaks. */
export function RichText({ text = '' }) {
  const inline = (s, k) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith('**') ? <strong key={`${k}-${i}`} className="font-semibold text-ink">{p.slice(2, -2)}</strong> : <span key={`${k}-${i}`}>{p}</span>)
  const out = []
  let bullets = []
  const flush = (k) => { if (bullets.length) { out.push(<ul key={`ul-${k}`} className="my-1 list-disc space-y-0.5 pl-5">{bullets}</ul>); bullets = [] } }
  text.split('\n').forEach((ln, i) => {
    const m = ln.match(/^\s*(?:[-•*])\s+(.*)$/)
    if (m) { bullets.push(<li key={i}>{inline(m[1], i)}</li>); return }
    flush(i)
    out.push(ln.trim() === '' ? <div key={i} className="h-1.5" /> : <p key={i}>{inline(ln, i)}</p>)
  })
  flush('end')
  return <div className="space-y-0.5 text-[13.5px] leading-relaxed text-ink-2">{out}</div>
}
