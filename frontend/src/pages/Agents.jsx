import { Activity, Boxes, CalendarClock, Languages, ShieldAlert, Truck } from 'lucide-react'
import { useFetch } from '../ctx'
import { Badge, Panel, Spinner } from '../ui'

const ICON = { 'Tracking Agent': Boxes, 'Supply Agent': Truck, 'Scheduling Agent': CalendarClock, 'Monitoring Agent': ShieldAlert, 'Language Agent': Languages }
const DESC = {
  'Tracking Agent': 'Component lifecycle: ordered → received → inspected → warehouse → bay → installed.',
  'Supply Agent': 'Inventory, shortages, supplier delays, replacement orders.',
  'Scheduling Agent': 'FCFS / Priority / Genetic Algorithm / CP-SAT with binding-constraint explanations.',
  'Monitoring Agent': 'Detects delays, rejections, downtime, maintenance and late tasks; raises alerts.',
  'Language Agent': 'PyTorch Micro LM (intent + entities); optional Qwen wording layer.',
}
const FLOW = ['Micro LM understand', 'Route', 'Tracking / Supply / Scheduling / Monitoring', 'Compose (optional Qwen)']

export default function Agents() {
  const { data, loading } = useFetch('/agents', 5000)
  if (loading || !data) return <Spinner />
  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel title="Orchestration (LangGraph)" className="col-span-12">
        <div className="flex flex-wrap items-center gap-2 text-xs">{FLOW.map((f, i) => (<span key={f} className="flex items-center gap-2"><Badge tone="blue">{f}</Badge>{i < FLOW.length - 1 && <span className="text-slate-500">→</span>}</span>))}</div>
      </Panel>
      {data.agents.map((a) => { const I = ICON[a.name] || Activity; return (
        <Panel key={a.name} className="col-span-12 md:col-span-6 xl:col-span-4">
          <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-lg bg-space-600 text-accent-soft"><I size={20} /></div>
            <div className="flex-1"><div className="font-semibold text-white">{a.name}</div><div className="text-xs text-slate-400">{DESC[a.name]}</div></div>
            <Badge tone={a.status === 'ACTIVE' ? 'green' : 'amber'}>{a.status}</Badge></div>
          <div className="mt-3 rounded bg-space-900/60 p-2 text-xs text-slate-300">{a.last_action}</div>
          <div className="mt-2 text-[11px] text-slate-500">{a.actions} actions logged</div>
        </Panel>) })}
      <Panel title="Agent activity log" className="col-span-12" bodyClass="max-h-96 overflow-y-auto">
        <ul className="space-y-1.5 text-xs">{data.log.map((l, i) => (<li key={i} className="flex gap-3 border-b border-line/40 pb-1.5"><span className="w-28 shrink-0 text-slate-500">{l.time}</span><span className="w-32 shrink-0 text-accent-soft">{l.agent}</span><span className="text-slate-300">{l.message}</span></li>))}</ul>
      </Panel>
    </div>
  )
}
