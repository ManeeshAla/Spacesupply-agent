import { useMemo, useState } from 'react'
import { STAGE_COLORS, cx, fmtDate, hourToDate, nice } from '../ui'

const ROW = 40
const LABEL_W = 150
// label colour per ordinal-ramp step: dark ink on the two light steps, white on the two dark ones
const STAGE_TEXT = { 1: 'rgb(13 13 13)', 2: 'rgb(13 13 13)', 3: 'rgb(255 255 255)', 4: 'rgb(255 255 255)' }

export default function Gantt({ data, onSelect, selected }) {
  const [hover, setHover] = useState(null)
  const { tasks, workstations, now_hour: now, start_iso: startIso } = data
  const ppx = 5.2                                   // pixels per hour
  const lo = Math.floor((data.min_hour - 6) / 24) * 24
  const hi = Math.ceil((data.max_hour + 12) / 24) * 24
  const width = (hi - lo) * ppx
  const x = (h) => (h - lo) * ppx
  const days = useMemo(() => { const a = []; for (let h = lo; h <= hi; h += 24) a.push(h); return a }, [lo, hi])
  const byWs = useMemo(() => {
    const m = {}
    tasks.forEach((t) => { if (t.workstation && t.start_hour != null) (m[t.workstation] ||= []).push(t) })
    return m
  }, [tasks])
  const sel = tasks.find((t) => t.id === selected)
  const related = new Set(sel ? [...sel.depends_on, ...tasks.filter((t) => t.depends_on.includes(sel.id)).map((t) => t.id)] : [])

  return (
    <div className="relative overflow-x-auto rounded-lg border border-hairline bg-surface-0">
      <div style={{ width: width + LABEL_W, minWidth: '100%' }} className="relative">
        {/* header */}
        <div className="sticky top-0 z-10 flex h-9 border-b border-hairline bg-surface-1">
          <div style={{ width: LABEL_W }} className="sticky left-0 z-20 shrink-0 border-r border-hairline bg-surface-1 px-3 py-2 text-xs font-medium text-ink-3">Workstation</div>
          <div className="relative flex-1">
            {days.map((h) => (
              <div key={h} style={{ left: x(h) }} className="absolute top-0 h-full border-l border-hairline pl-1.5 pt-2 text-[11px] tabular text-ink-muted">
                {hourToDate(startIso, h).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
              </div>
            ))}
          </div>
        </div>
        {/* rows */}
        {workstations.map((w) => (
          <div key={w.id} className="flex border-b border-hairline/70 last:border-0" style={{ height: ROW }}>
            <div style={{ width: LABEL_W }} className="sticky left-0 z-10 shrink-0 border-r border-hairline bg-surface-1 px-3 py-1.5">
              <div className="mono text-xs font-semibold text-ink">{w.id}{w.status === 'DOWN' && <span className="ml-1.5 font-sans text-t-critical">● down</span>}</div>
              <div className="truncate text-[11px] text-ink-3">{w.name}</div>
            </div>
            <div className="relative flex-1">
              {days.map((h) => <div key={h} style={{ left: x(h) }} className="absolute top-0 h-full border-l border-hairline/50" />)}
              {w.status === 'DOWN' && <div className="absolute top-1 h-[30px] rounded bg-critical/15 ring-1 ring-critical/40" style={{ left: x(now), width: w.free_in_hours * ppx }} title="Out of service" />}
              {(byWs[w.id] || []).map((t) => {
                const done = t.status === 'COMPLETED'
                const late = t.late_hours > 0
                return (
                  <button key={t.id} onClick={() => onSelect(t.id)} onMouseEnter={() => setHover(t)} onMouseLeave={() => setHover(null)}
                          onFocus={() => setHover(t)} onBlur={() => setHover(null)} aria-label={`${t.id} ${t.name}`}
                          className={cx('absolute top-1.5 h-[28px] overflow-hidden rounded px-1.5 text-left text-[11px] font-semibold leading-[28px] transition-shadow',
                            t.status === 'IN_PROGRESS' && 'running',
                            selected === t.id ? 'ring-2 ring-ink' : related.has(t.id) ? 'ring-2 ring-accent' : late ? 'ring-2 ring-critical' : 'ring-1 ring-black/20')}
                          style={{ left: x(t.start_hour), width: Math.max(18, t.duration * ppx - 2), background: STAGE_COLORS[t.stage_id], color: STAGE_TEXT[t.stage_id], opacity: done ? 0.45 : 1 }}>
                    {t.id.replace('T-', '')}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        {/* now line */}
        <div className="pointer-events-none absolute top-0 z-10 h-full w-px bg-accent" style={{ left: LABEL_W + x(now) }}>
          <span className="absolute left-1 top-10 rounded bg-accent-solid px-1 text-[10px] font-semibold text-accent-ink">Now</span>
        </div>
      </div>
      {hover && (
        <div role="tooltip" className="panel pointer-events-none fixed bottom-4 left-1/2 z-40 w-[min(520px,92vw)] -translate-x-1/2 p-3 text-xs shadow-lg">
          <div className="text-[13px] font-semibold text-ink"><span className="mono text-ink-3">{hover.id}</span> · {hover.name}</div>
          <div className="mt-1 leading-relaxed text-ink-2">
            {nice(hover.status)} · {hover.workstation} · {hover.duration} h · priority {hover.priority}<br />
            {fmtDate(hourToDate(startIso, hover.start_hour))} → {fmtDate(hourToDate(startIso, hover.end_hour))} · deadline {fmtDate(hourToDate(startIso, hover.deadline_hour))}
            {hover.late_hours > 0 && <span className="ml-1 font-semibold text-t-critical">({hover.late_hours} h late)</span>}
          </div>
          {hover.reason_text && <div className="mt-1 text-ink-3">{hover.reason_text}</div>}
        </div>
      )}
    </div>
  )
}
