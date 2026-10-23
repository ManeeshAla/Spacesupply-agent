import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import Gantt from '../components/Gantt'
import { post } from '../api'
import { useApp, useFetch } from '../ctx'
import { Badge, Panel, STAGE_COLORS, Spinner, fmtDate, hourToDate, nice, sign, statusTone } from '../ui'

export default function Schedule({ openTask }) {
  const { bump, filters } = useApp()
  const { data, loading } = useFetch('/schedule', 10000)
  const [algo, setAlgo] = useState('CPSAT')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [flt, setFlt] = useState('ACTIVE')
  // the chat can set this filter for us ("show late tasks", "show stage 2's plan")
  useEffect(() => { if (filters.schedule) setFlt(String(filters.schedule)) }, [filters.schedule])
  if (loading || !data) return <Spinner />
  const m = data.version.metrics
  const replan = async () => {
    setBusy(true); setMsg('')
    try { const r = await post('/schedule/replan', { algorithm: algo }); setMsg(`${algo}: makespan ${r.metrics.makespan}h, ${r.metrics.tardy_tasks} late, ${r.changes.length} task(s) moved (${Math.round(r.metrics.runtime_ms)} ms)`); bump() }
    catch (e) { setMsg(e.message) } finally { setBusy(false) }
  }
  const rows = data.tasks.filter((t) => (flt === 'ALL' ? true : flt === 'ACTIVE' ? t.status !== 'COMPLETED' : flt === 'LATE' ? t.late_hours > 0 : flt === 'MOVED' ? t.shift_hours !== 0 : t.stage_id === +flt))
    .sort((a, b) => (a.start_hour ?? 0) - (b.start_hour ?? 0))
  return (
    <div className="space-y-4">
      <Panel title="Assembly schedule · Gantt"
             right={<div className="flex flex-wrap items-center gap-2">
               {[1, 2, 3, 4].map((s) => <span key={s} className="flex items-center gap-1 text-[11px] text-slate-400"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: STAGE_COLORS[s] }} />S{s}</span>)}
               <select className="input" value={algo} onChange={(e) => setAlgo(e.target.value)}>
                 <option value="CPSAT">OR-Tools CP-SAT</option><option value="GA">Genetic Algorithm</option><option value="PRIORITY">Priority rule</option><option value="FCFS">FCFS baseline</option></select>
               <button className="btn btn-primary" disabled={busy} onClick={replan}><RefreshCw size={14} className={busy ? 'animate-spin' : ''} />Re-plan</button></div>}>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-slate-300">
          <Badge tone="blue">Plan v{data.version.id} · {data.version.algorithm}</Badge><Badge tone="slate">trigger: {data.version.trigger}</Badge>
          <Badge tone="cyan">makespan {m.makespan}h</Badge><Badge tone={m.tardy_tasks ? 'red' : 'green'}>{m.tardy_tasks} late task(s)</Badge>
          <Badge tone="slate">utilisation {(m.utilization * 100).toFixed(0)}%</Badge><Badge tone="green">{m.conflicts} conflicts</Badge>{msg && <span className="text-accent-soft">{msg}</span>}
        </div>
        <Gantt data={data} onSelect={openTask} />
        <p className="mt-2 text-[11px] text-slate-500">Bars: faded = completed, striped = running, red ring = projected past deadline. Click a bar for the full explanation. Hover for details.</p>
      </Panel>
      <Panel title={`Tasks (${rows.length})`} right={<select className="input" value={flt} onChange={(e) => setFlt(e.target.value)}>
        <option value="ACTIVE">Not completed</option><option value="ALL">All</option><option value="LATE">Projected late</option><option value="MOVED">Rescheduled</option>{[1, 2, 3, 4].map((s) => <option key={s} value={s}>Stage {s}</option>)}</select>}>
        <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight: 440 }}>
          <table className="w-full"><thead className="sticky top-0 bg-space-700"><tr>{['Task', 'Name', 'WS', 'Start', 'End', 'Prio', 'Deadline', 'Status', 'Depends on', 'Why this time'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{rows.map((t) => (
              <tr key={t.id} onClick={() => openTask(t.id)} className="cursor-pointer border-t border-line/50 align-top hover:bg-space-700/60">
                <td className="td font-mono text-xs">{t.id}</td><td className="td">{t.name}</td><td className="td">{t.workstation}</td>
                <td className="td whitespace-nowrap text-xs">{fmtDate(hourToDate(data.start_iso, t.start_hour))}{t.shift_hours !== 0 && <Badge tone={t.shift_hours > 0 ? 'amber' : 'green'} className="ml-1">{sign(t.shift_hours)}</Badge>}</td>
                <td className="td whitespace-nowrap text-xs">{fmtDate(hourToDate(data.start_iso, t.end_hour))}</td><td className="td">{t.priority}</td>
                <td className="td whitespace-nowrap text-xs">{fmtDate(hourToDate(data.start_iso, t.deadline_hour))}{t.late_hours > 0 && <Badge tone="red" className="ml-1">+{t.late_hours}h late</Badge>}</td>
                <td className="td"><Badge tone={statusTone(t.status)}>{nice(t.status)}</Badge></td><td className="td text-xs text-slate-400">{t.depends_on.join(', ') || '—'}</td>
                <td className="td max-w-xs text-xs text-slate-400">{t.reason_text || ''}</td></tr>))}</tbody></table>
        </div>
      </Panel>
      <Panel title="Workstations">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">{data.workstations.map((w) => (
          <div key={w.id} className="rounded-lg border border-line bg-space-900/60 p-3"><div className="flex items-center justify-between"><b className="text-sm text-white">{w.id}</b>
            <Badge tone={w.status === 'DOWN' ? 'red' : w.current_task ? 'cyan' : 'green'}>{w.status === 'DOWN' ? 'DOWN' : w.current_task ? 'busy' : 'free'}</Badge></div>
            <div className="mt-1 text-xs text-slate-400">{w.name}</div>
            <div className="mt-2 text-xs text-slate-300">{w.current_task ? `Running ${w.current_task}` : 'Idle'}{w.free_in_hours > 0 && ` · free in ${w.free_in_hours}h`}</div>
            {w.maintenance_in_hours != null && w.maintenance_in_hours >= 0 && <div className="mt-1 text-[11px] text-amber-300">Maintenance in {Math.round(w.maintenance_in_hours / 24)}d</div>}</div>))}</div>
      </Panel>
    </div>
  )
}
