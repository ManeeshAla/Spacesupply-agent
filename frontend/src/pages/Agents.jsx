import { ArrowRight, Boxes, CalendarClock, Languages, ShieldAlert, Truck } from 'lucide-react'
import AgentBus from '../components/AgentBus'
import { useFetch } from '../ctx'
import { Badge, PageHeader, Panel, Spinner } from '../ui'

const ICON = { 'Tracking Agent': Boxes, 'Supply Agent': Truck, 'Scheduling Agent': CalendarClock, 'Monitoring Agent': ShieldAlert, 'Language Agent': Languages }
const DESC = {
  'Tracking Agent': 'Component lifecycle: ordered → received → inspected → warehouse → bay → installed.',
  'Supply Agent': 'Inventory, shortages, supplier delays and replacement orders.',
  'Scheduling Agent': 'FCFS, Priority, Genetic Algorithm and OR-Tools CP-SAT, with binding-constraint explanations.',
  'Monitoring Agent': 'Detects delays, rejections, downtime, maintenance and late tasks, and raises alerts.',
  'Language Agent': 'PyTorch Micro LM (intent and entities) plus the Gemini supervisor with tool calling.',
}
const CHAT_FLOW = ['Micro LM hint', 'Gemini supervisor', 'Tools → specialist agents', 'Grounding guard', 'Answer']
const EVENT_FLOW = ['Disruption', 'Published on the bus', 'Scheduling re-plans (CP-SAT)', 'Monitoring scans and alerts']

function Flow({ steps, note }) {
  return (
    <>
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-2">
        {steps.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className="rounded-lg border border-hairline bg-surface-0 px-2.5 py-1 text-[13px] text-ink-2">{s}</span>
            {i < steps.length - 1 && <ArrowRight size={13} className="text-ink-muted" />}
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs leading-relaxed text-ink-3">{note}</p>
    </>
  )
}

export default function Agents() {
  const { data, loading } = useFetch('/agents', 5000)
  if (loading || !data) return <Spinner />
  return (
    <div className="space-y-5">
      <PageHeader title="Agents" description="Five specialist agents. They talk to each other over a message bus, and the assistant can call them as tools." />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title="When you ask a question" subtitle="LangGraph supervisor with Gemini tool calling">
          <Flow steps={CHAT_FLOW} note="The assistant can only answer from what a tool returned. An id or number it invents is caught and the answer is replaced." />
        </Panel>
        <Panel title="When something goes wrong" subtitle="Agents subscribe to topics instead of being called in a fixed order">
          <Flow steps={EVENT_FLOW} note="In-process publish/subscribe between agent objects — not a distributed broker." />
        </Panel>
      </div>

      <AgentBus height={360} bodyClass="overflow-y-auto" />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.agents.map((a) => {
          const I = ICON[a.name] || Boxes
          return (
            <Panel key={a.name}>
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-t-accent"><I size={18} /></div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-semibold text-ink">{a.name}</div>
                    <Badge tone={a.status === 'ACTIVE' ? 'green' : 'amber'} dot>{a.status === 'ACTIVE' ? 'Active' : a.status}</Badge>
                  </div>
                  <p className="mt-0.5 text-xs leading-relaxed text-ink-3">{DESC[a.name]}</p>
                </div>
              </div>
              <div className="mt-3 rounded-lg bg-surface-0 px-3 py-2 text-xs leading-relaxed text-ink-2">{a.last_action}</div>
              <div className="mt-2 text-[11px] tabular text-ink-muted">{a.actions} actions logged</div>
            </Panel>
          )
        })}
      </div>

      <Panel flush title="Activity log" height={380} bodyClass="overflow-y-auto">
        <ul>
          {data.log.map((l, i) => (
            <li key={i} className="flex gap-4 border-b border-hairline/60 px-4 py-2 text-[13px] last:border-0">
              <span className="w-28 shrink-0 text-xs tabular text-ink-muted">{l.time}</span>
              <span className="w-32 shrink-0 text-xs font-medium text-ink-3">{l.agent}</span>
              <span className="text-ink-2">{l.message}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
