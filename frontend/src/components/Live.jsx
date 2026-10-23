import { useEffect, useRef } from 'react'
import { Activity, AlertTriangle, CalendarClock, CheckCircle2, Pause, Play, RotateCcw, Shuffle, Truck, Zap } from 'lucide-react'
import { useApp } from '../ctx'
import { Badge } from '../ui'

const SPEEDS = [1, 2, 4, 8]

export function LiveControls({ compact = false }) {
  const { live } = useApp()
  return (
    <div className="flex items-center gap-2">
      <button onClick={() => live.setRunning(!live.running)} className={`btn ${live.running ? 'btn-danger' : 'btn-primary'}`}>
        {live.running ? <><Pause size={14} />Pause</> : <><Play size={14} />Play</>}
      </button>
      <div className="flex overflow-hidden rounded-lg border border-line">
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => live.setSpeed(s)}
                  className={`px-2 py-1.5 text-xs font-semibold transition ${live.speed === s ? 'bg-accent text-white' : 'bg-space-600 text-slate-300 hover:bg-space-500'}`}>{s}×</button>
        ))}
      </div>
      <button onClick={() => live.setChaos(!live.chaos)} title="Randomly inject supplier delays, failed inspections and workstation outages"
              className={`btn ${live.chaos ? '!border-warn/50 !bg-warn/15 !text-amber-200' : ''}`}>
        <Shuffle size={14} />{compact ? '' : 'Random events'} {live.chaos ? 'on' : 'off'}
      </button>
      {!compact && <button onClick={live.reset} className="btn" title="Reset the simulation to its initial state"><RotateCcw size={14} /></button>}
    </div>
  )
}

const ICON = { TASK: CalendarClock, LOGISTICS: Truck, ALERT: AlertTriangle, DISRUPTION: Zap, REPLAN: Activity, SYSTEM: CheckCircle2 }
const TONE = { TASK: 'blue', LOGISTICS: 'cyan', ALERT: 'amber', DISRUPTION: 'red', REPLAN: 'violet', SYSTEM: 'slate' }

export function LiveFeed() {
  const { live } = useApp()
  const box = useRef(null)
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight }, [live.feed.length])
  return (
    <div ref={box} className="h-full overflow-y-auto pr-1">
      {live.feed.length === 0 && (
        <p className="p-3 text-sm text-slate-400">
          Press <b className="text-slate-200">Play</b> to run the assembly line. The clock advances on its own, parts arrive and get inspected, tasks start and finish — and with random events on, the agents handle disruptions live.
        </p>
      )}
      <ul className="space-y-1">
        {live.feed.map((f) => {
          const I = ICON[f.kind] || Activity
          return (
            <li key={f.id} className={`flex items-start gap-2 rounded-lg px-2 py-1.5 text-xs ${f.kind === 'DISRUPTION' ? 'bg-bad/10' : f.kind === 'REPLAN' ? 'bg-violet/10' : 'bg-space-900/40'}`}>
              <I size={13} className={`mt-0.5 shrink-0 ${f.severity === 'CRITICAL' ? 'text-bad' : f.severity === 'WARNING' ? 'text-warn' : 'text-slate-400'}`} />
              <span className="w-24 shrink-0 text-slate-500">{f.time}</span>
              <span className="flex-1 text-slate-200">{f.text}</span>
              <Badge tone={TONE[f.kind] || 'slate'}>{f.kind.toLowerCase()}</Badge>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function LiveDot() {
  const { live } = useApp()
  return <span className={`h-2 w-2 rounded-full ${live.running ? 'dot-live bg-ok' : 'bg-slate-500'}`} />
}
