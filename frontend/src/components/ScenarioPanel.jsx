import { useState } from 'react'
import { Clock, Play, RotateCcw, Truck, Wrench, XCircle } from 'lucide-react'
import { post } from '../api'
import { useApp, useFetch } from '../ctx'
import { Badge, Drawer, Spinner, sign } from '../ui'

const AGENT_TONE = { 'Supply Agent': 'amber', 'Scheduling Agent': 'blue', 'Monitoring Agent': 'red', 'Tracking Agent': 'cyan' }

function Card({ icon: Icon, title, desc, children }) {
  return (
    <div className="rounded-xl border border-line bg-space-900/60 p-4">
      <div className="mb-1 flex items-center gap-2 font-semibold text-white"><Icon size={16} className="text-accent-soft" />{title}</div>
      <p className="mb-3 text-xs text-slate-400">{desc}</p>
      {children}
    </div>
  )
}

export default function ScenarioPanel({ open, onClose, onDone }) {
  const { bump } = useApp()
  const deliveries = useFetch('/deliveries')
  const comps = useFetch('/components')
  const sched = useFetch('/schedule')
  const [busy, setBusy] = useState(false)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [cid, setCid] = useState('CMP-021')
  const [hours, setHours] = useState(24)
  const [rej, setRej] = useState('')
  const [ws, setWs] = useState('WS-04')
  const [wsh, setWsh] = useState(24)

  const run = async (body) => {
    setBusy(true); setError(''); setReport(null)
    try { const r = await post(body.type === 'RESET' ? '/reset' : '/simulate', body); setReport(body.type === 'RESET' ? { reset: true } : r); bump(); onDone?.() }
    catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const open_d = (deliveries.data || []).filter((d) => d.status !== 'ARRIVED')
  const rejectable = (comps.data || []).filter((c) => ['IN_INSPECTION', 'INSPECTION_PENDING', 'RECEIVED', 'IN_WAREHOUSE', 'APPROVED'].includes(c.status))

  return (
    <Drawer open={open} onClose={onClose} title="Scenario control · inject events" width="max-w-2xl">
      <p className="mb-4 text-sm text-slate-400">Inject a real-world disruption. The agents respond autonomously: Supply/Tracking apply it, the Scheduling Agent re-optimises with OR-Tools CP-SAT, and the Monitoring Agent raises alerts.</p>
      <div className="grid gap-3 md:grid-cols-2">
        <Card icon={Truck} title="Supplier delay" desc="A supplier reports a late delivery.">
          <select className="input mb-2 w-full" value={cid} onChange={(e) => setCid(e.target.value)}>
            {open_d.map((d) => <option key={d.id} value={d.component_id}>{d.component_id} · {d.component} (ETA +{d.eta_hours}h)</option>)}
          </select>
          <div className="mb-2 flex items-center gap-2 text-sm"><input type="range" min="6" max="96" step="6" value={hours} onChange={(e) => setHours(+e.target.value)} className="flex-1" /><span className="w-12 text-right">{hours}h</span></div>
          <button className="btn btn-primary w-full" disabled={busy} onClick={() => run({ type: 'SUPPLIER_DELAY', component_id: cid, hours })}><Play size={14} />Delay delivery</button>
        </Card>
        <Card icon={XCircle} title="Reject a component" desc="A part fails inspection; a replacement is ordered.">
          <select className="input mb-2 w-full" value={rej} onChange={(e) => setRej(e.target.value)}>
            <option value="">Select component…</option>
            {rejectable.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.name} ({c.status.toLowerCase().replace(/_/g, ' ')})</option>)}
          </select>
          <button className="btn btn-danger w-full" disabled={busy || !rej} onClick={() => run({ type: 'REJECT_COMPONENT', component_id: rej })}><Play size={14} />Fail inspection</button>
        </Card>
        <Card icon={Wrench} title="Workstation breakdown" desc="A workstation goes out of service.">
          <select className="input mb-2 w-full" value={ws} onChange={(e) => setWs(e.target.value)}>
            {(sched.data?.workstations || []).map((w) => <option key={w.id} value={w.id}>{w.id} · {w.name}</option>)}
          </select>
          <div className="mb-2 flex items-center gap-2 text-sm"><input type="range" min="6" max="72" step="6" value={wsh} onChange={(e) => setWsh(+e.target.value)} className="flex-1" /><span className="w-12 text-right">{wsh}h</span></div>
          <button className="btn btn-danger w-full" disabled={busy} onClick={() => run({ type: 'WORKSTATION_DOWN', workstation_id: ws, hours: wsh })}><Play size={14} />Take offline</button>
        </Card>
        <Card icon={Clock} title="Advance time" desc="Run the factory clock forward: deliveries arrive, parts clear inspection, tasks start and finish.">
          <div className="grid grid-cols-4 gap-2">{[6, 12, 24, 48].map((h) => <button key={h} className="btn justify-center" disabled={busy} onClick={() => run({ type: 'ADVANCE_TIME', hours: h })}>+{h}h</button>)}</div>
          <button className="btn mt-2 w-full" disabled={busy} onClick={() => { if (confirm('Reset the whole scenario to its initial state?')) run({ type: 'RESET' }) }}><RotateCcw size={14} />Reset scenario</button>
        </Card>
      </div>
      {busy && <Spinner label="Agents are responding… (OR-Tools is re-planning)" />}
      {error && <div className="mt-4 rounded-lg border border-bad/40 bg-bad/10 p-3 text-sm text-red-200">{error}</div>}
      {report?.reset && <div className="mt-4 rounded-lg border border-ok/40 bg-ok/10 p-3 text-sm text-green-200">Scenario reset.</div>}
      {report && !report.reset && (
        <div className="mt-5 space-y-4">
          <h3 className="panel-title">Autonomous response</h3>
          <ol className="space-y-2">{report.steps.map((s, i) => (
            <li key={i} className="flex gap-3 rounded-lg border border-line bg-space-900/60 p-3 text-sm"><Badge tone={AGENT_TONE[s.agent] || 'slate'} className="h-fit shrink-0">{s.agent}</Badge><span>{s.action}</span></li>))}
          </ol>
          {report.before && (
            <div className="grid grid-cols-3 gap-3 text-center text-sm">
              {[['Late tasks', 'tardy_tasks'], ['Weighted lateness', 'weighted_tardiness'], ['Launch review', 'launch_readiness']].map(([label, k]) => (
                <div key={k} className="rounded-lg border border-line bg-space-900/60 p-3"><div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
                  <div className="mt-1 font-semibold text-white">{report.before[k]} → <span className={report.after[k] !== report.before[k] ? 'text-amber-300' : ''}>{report.after[k]}</span></div></div>))}
            </div>
          )}
          {report.schedule_changes?.length > 0 && (
            <div>
              <h4 className="panel-title mb-2">Tasks rescheduled ({report.schedule_changes.length})</h4>
              <ul className="space-y-1.5 text-sm">{report.schedule_changes.slice(0, 8).map((c) => (
                <li key={c.task_id} className="rounded-lg border border-line bg-space-900/60 p-2.5"><b>{c.task_id}</b> {c.name} <Badge tone={c.delta_hours > 0 ? 'amber' : 'green'}>{sign(c.delta_hours)}</Badge>
                  <div className="mt-0.5 text-xs text-slate-400">{c.reason}</div></li>))}</ul>
            </div>
          )}
          {report.changes && <ul className="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-300">{report.changes.map((c, i) => <li key={i}>• {c}</li>)}</ul>}
        </div>
      )}
    </Drawer>
  )
}
