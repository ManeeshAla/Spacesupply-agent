import { useEffect, useRef } from 'react'
import { Activity, AlertTriangle, CalendarClock, CheckCircle2, Pause, Play, RotateCcw, Shuffle, Truck, Zap } from 'lucide-react'
import { useApp } from '../ctx'
import { cx } from '../ui'

const SPEEDS = [1, 2, 4, 8]

/**
 * Play/Pause + speed + random events (+ reset). Used in the top bar and inside the Dashboard's
 * Live activity panel. The data-testid hooks are what the end-to-end live check drives.
 */
export function LiveControls({ compact = false }) {
  const { live } = useApp()
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button onClick={() => live.setRunning(!live.running)} data-testid="live-play" data-state={live.running ? 'running' : 'paused'}
              className={cx('btn', live.running ? 'btn-danger' : 'btn-primary')}>
        {live.running ? <><Pause size={14} />Pause</> : <><Play size={14} />Play</>}
      </button>
      <div className="inline-flex rounded-lg border border-hairline bg-surface-0 p-0.5" role="group" aria-label="Simulation speed">
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => live.setSpeed(s)} data-testid={`live-speed-${s}`} aria-pressed={live.speed === s}
                  className={cx('rounded-md px-2 py-1 text-xs font-medium tabular transition-colors',
                    live.speed === s ? 'bg-surface-1 text-ink shadow-sm ring-1 ring-hairline' : 'text-ink-3 hover:text-ink')}>{s}×</button>
        ))}
      </div>
      <button onClick={() => live.setChaos(!live.chaos)} data-testid="live-chaos" data-state={live.chaos ? 'on' : 'off'}
              title="Randomly inject supplier delays, failed inspections and workstation outages" className="btn">
        <Shuffle size={14} className={live.chaos ? 'text-t-warning' : 'text-ink-muted'} />{compact ? 'Random' : 'Random events'}
        <span className={cx('font-semibold', live.chaos ? 'text-t-warning' : 'text-ink-muted')}>{live.chaos ? 'on' : 'off'}</span>
      </button>
      {!compact && (
        <button onClick={live.reset} className="btn btn-ghost !px-2" title="Reset the simulation to its initial state" aria-label="Reset simulation">
          <RotateCcw size={14} />
        </button>
      )}
    </div>
  )
}

const ICON = { TASK: CalendarClock, LOGISTICS: Truck, ALERT: AlertTriangle, DISRUPTION: Zap, REPLAN: Activity, SYSTEM: CheckCircle2 }
const KIND_TONE = { DISRUPTION: 'text-t-critical', REPLAN: 'text-t-violet', ALERT: 'text-t-warning', TASK: 'text-t-accent', LOGISTICS: 'text-t-aqua', SYSTEM: 'text-ink-3' }

/** The running commentary. Rows are quiet text; only disruptions and re-plans carry colour. */
export function LiveFeed() {
  const { live } = useApp()
  const box = useRef(null)
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight }, [live.feed.length])
  return (
    <div ref={box} className="h-full overflow-y-auto pr-1" data-testid="live-feed">
      {live.feed.length === 0 && (
        <div className="flex h-full flex-col items-center justify-center gap-1.5 px-6 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-ink-muted"><Play size={16} /></div>
          <p className="text-sm font-medium text-ink">The line is idle</p>
          <p className="max-w-sm text-[13px] text-ink-3">
            Press <b className="font-medium text-ink">Play</b> and the clock advances: parts arrive and get inspected, tasks start and finish, and with random events on the agents handle disruptions live.
          </p>
        </div>
      )}
      <ul>
        {live.feed.map((f) => {
          const I = ICON[f.kind] || Activity
          const hot = f.kind === 'DISRUPTION' || f.kind === 'REPLAN'
          return (
            <li key={f.id} data-testid="live-feed-item" data-kind={f.kind}
                className={cx('flex items-start gap-2.5 border-b border-hairline/60 px-1 py-2 text-[13px] last:border-0', hot && '-mx-1 rounded-md px-2')}
                style={hot ? { background: f.kind === 'DISRUPTION' ? 'rgb(var(--critical) / 0.08)' : 'rgb(var(--violet) / 0.08)' } : undefined}>
              <I size={14} className={cx('mt-0.5 shrink-0', KIND_TONE[f.kind] || 'text-ink-3')} />
              <span className="flex-1 text-ink-2">{f.text}</span>
              <span className="shrink-0 text-xs tabular text-ink-muted">{f.time}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function LiveDot() {
  const { live } = useApp()
  return <span className={cx('h-2 w-2 rounded-full', live.running ? 'dot-live bg-good' : 'bg-ink-muted')} />
}
