import { Activity, Boxes, CalendarClock, Languages, ShieldAlert, Truck } from 'lucide-react'
import AgentBus from '../components/AgentBus'
import { useFetch } from '../ctx'
import { Badge, Panel, Spinner } from '../ui'

const ICON = { 'Tracking Agent': Boxes, 'Supply Agent': Truck, 'Scheduling Agent': CalendarClock, 'Monitoring Agent': ShieldAlert, 'Language Agent': Languages }
const DESC = {
  'Tracking Agent': 'Component lifecycle: ordered → received → inspected → warehouse → bay → installed.',
  'Supply Agent': 'Inventory, shortages, supplier delays, replacement orders.',
  'Scheduling Agent': 'FCFS / Priority / Genetic Algorithm / CP-SAT with binding-constraint explanations.',
  'Monitoring Agent': 'Detects delays, rejections, downtime, maintenance and late tasks; raises alerts.',
  'Language Agent': 'PyTorch Micro LM (intent + entities) + Gemini supervisor with tool calling; Qwen wording layer optional.',
}
const CHAT_FLOW = ['Micro LM hint', 'Gemini supervisor', 'Tool calls → specialist agents', 'Grounding guard', 'Answer']
const EVENT_FLOW = ['Disruption', 'publish on bus', 'Scheduling re-plans (CP-SAT)', 'Monitoring scans + alerts']

export default function Agents() {
  const { data, loading } = useFetch('/agents', 5000)
  if (loading || !data) return <Spinner />
  const Flow = ({ steps, tone }) => (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {steps.map((f, i) => (
        <span key={f} className="flex items-center gap-2">
          <Badge tone={tone}>{f}</Badge>{i < steps.length - 1 && <span className="text-slate-500">→</span>}
        </span>
      ))}
    </div>
  )
  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel title="Chat orchestration (LangGraph + Gemini tool calling)" className="col-span-12 xl:col-span-6">
        <Flow steps={CHAT_FLOW} tone="blue" />
        <p className="mt-2 text-[11px] text-slate-500">
          The supervisor can only answer from what a tool returned; any id or number it invents is caught and
          the answer is replaced.
        </p>
      </Panel>
      <Panel title="Event orchestration (message bus)" className="col-span-12 xl:col-span-6">
        <Flow steps={EVENT_FLOW} tone="amber" />
        <p className="mt-2 text-[11px] text-slate-500">
          Agents subscribe to topics instead of being called in a fixed order. In-process pub/sub, not a
          distributed broker.
        </p>
      </Panel>
      <AgentBus className="col-span-12" />
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
