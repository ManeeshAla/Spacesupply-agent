import { useMemo, useState } from 'react'
import { STAGE_COLORS, fmtDate, hourToDate, nice } from '../ui'

const ROW = 40
const LABEL_W = 150

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
    <div className="relative overflow-x-auto rounded-lg border border-line bg-space-900/60">
      <div style={{ width: width + LABEL_W, minWidth: '100%' }} className="relative">
        {/* header */}
        <div className="sticky top-0 z-10 flex h-9 border-b border-line bg-space-800">
          <div style={{ width: LABEL_W }} className="sticky left-0 z-20 shrink-0 border-r border-line bg-space-800 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Workstation</div>
          <div className="relative flex-1">
            {days.map((h) => (
              <div key={h} style={{ left: x(h) }} className="absolute top-0 h-full border-l border-line/70 pl-1.5 pt-2 text-[10px] text-slate-400">
                {hourToDate(startIso, h).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}
              </div>
            ))}
          </div>
        </div>
        {/* rows */}
        {workstations.map((w) => (
          <div key={w.id} className="flex border-b border-line/60" style={{ height: ROW }}>
            <div style={{ width: LABEL_W }} className="sticky left-0 z-10 shrink-0 border-r border-line bg-space-800 px-3 py-1.5">
              <div className="text-xs font-semibold text-slate-100">{w.id}{w.status === 'DOWN' && <span className="ml-1 text-bad">● DOWN</span>}</div>
              <div className="truncate text-[10px] text-slate-400">{w.name}</div>
            </div>
            <div className="relative flex-1">
              {days.map((h) => <div key={h} style={{ left: x(h) }} className="absolute top-0 h-full border-l border-line/30" />)}
              {w.status === 'DOWN' && <div className="absolute top-1 h-[30px] rounded bg-bad/20 ring-1 ring-bad/40" style={{ left: x(now), width: w.free_in_hours * ppx }} title="Out of service" />}
              {(byWs[w.id] || []).map((t) => {
                const done = t.status === 'COMPLETED'
                const late = t.late_hours > 0
                return (
                  <button key={t.id} onClick={() => onSelect(t.id)} onMouseEnter={() => setHover(t)} onMouseLeave={() => setHover(null)}
                          className={`absolute top-1.5 h-[28px] overflow-hidden rounded px-1.5 text-left text-[10px] font-semibold leading-[28px] text-white ring-1 transition
                            ${t.status === 'IN_PROGRESS' ? 'running' : ''} ${selected === t.id ? 'ring-2 ring-white' : related.has(t.id) ? 'ring-2 ring-cyan-300' : late ? 'ring-2 ring-bad' : 'ring-black/30'}`}
                          style={{ left: x(t.start_hour), width: Math.max(18, t.duration * ppx - 2), background: STAGE_COLORS[t.stage_id], opacity: done ? 0.4 : 1 }}>
                    <span className="drop-shadow">{t.id.replace("T-", "")}</span>
                  </button>
                )
              })}
            </div>
          </div>
        ))}
        {/* now line */}
        <div className="pointer-events-none absolute top-0 z-10 h-full w-px bg-cyan-300" style={{ left: LABEL_W + x(now) }}>
          <span className="absolute -top-0 left-1 rounded bg-cyan-300 px-1 text-[9px] font-bold text-space-900">NOW</span>
        </div>
      </div>
      {hover && (
        <div className="pointer-events-none fixed bottom-4 left-1/2 z-40 w-[min(520px,92vw)] -translate-x-1/2 rounded-lg border border-line bg-space-700 p-3 text-xs shadow-2xl">
          <div className="font-semibold text-white">{hover.id} · {hover.name}</div>
          <div className="mt-1 text-slate-300">
            {nice(hover.status)} · {hover.workstation} · {hover.duration}h · priority {hover.priority}<br />
            {fmtDate(hourToDate(startIso, hover.start_hour))} → {fmtDate(hourToDate(startIso, hover.end_hour))} · deadline {fmtDate(hourToDate(startIso, hover.deadline_hour))}
            {hover.late_hours > 0 && <span className="ml-1 font-semibold text-red-300">({hover.late_hours}h late)</span>}
          </div>
          {hover.reason_text && <div className="mt-1 text-slate-400">{hover.reason_text}</div>}
        </div>
      )}
    </div>
  )
}
