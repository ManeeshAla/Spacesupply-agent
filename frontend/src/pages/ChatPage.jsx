import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import AgentBus from '../components/AgentBus'
import Chat from '../components/Chat'
import { useApp, useFetch } from '../ctx'
import { Badge, PageHeader, Panel, cx } from '../ui'

const prettyTool = (t = '') => t.replace(/_/g, ' ')

/** The "how was this answer built" detail. Collapsed by default: internals are for the curious. */
function Provenance({ last, gem }) {
  const meta = last?.meta
  if (!meta) return <p className="text-[13px] text-ink-3">Ask something to see which tools were called and how the answer was checked.</p>
  return (
    <div className="space-y-4 text-[13px]">
      <div>
        <div className="eyebrow mb-1.5">Micro LM hint (local)</div>
        {last.microlm?.intent ? (
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="violet">{String(last.microlm.intent).replace(/_/g, ' ').toLowerCase()}{last.microlm.confidence != null && ` · ${(last.microlm.confidence * 100).toFixed(0)}%`}</Badge>
            {(last.microlm.entities || []).map((e, i) => <Badge key={i}>{e.type}: {e.text}</Badge>)}
          </div>
        ) : <span className="text-ink-3">not recorded</span>}
      </div>
      <div>
        <div className="eyebrow mb-1.5">Tools called</div>
        {meta.tools_called?.length ? (
          <ul className="space-y-1.5">
            {meta.tools_called.map((t, i) => (
              <li key={i} className="flex items-start justify-between gap-2">
                <span><Badge tone={t.ok === false ? 'red' : 'blue'}>{prettyTool(t.tool)}</Badge>
                  {t.args && Object.keys(t.args).length > 0 && <span className="mono ml-1.5 text-[11px] text-ink-muted">{JSON.stringify(t.args)}</span>}</span>
                {t.ms != null && <span className="shrink-0 text-xs tabular text-ink-muted">{t.ms} ms</span>}
              </li>
            ))}
          </ul>
        ) : <span className="text-ink-3">none — answered without plant data</span>}
      </div>
      <div>
        <div className="eyebrow mb-1.5">Grounding check</div>
        {meta.grounded === false ? <Badge tone="red">failed — draft replaced with the tool output</Badge>
          : <Badge tone="green">passed — every id and number came from a tool</Badge>}
      </div>
      <div className="text-xs text-ink-3">
        Answered by {meta.source === 'gemini' ? (meta.model || 'Gemini') : meta.source === 'microlm' ? 'the offline Micro LM and templates' : meta.source === 'action' ? 'a confirmed action' : meta.source}
        {meta.latency_ms != null && ` · ${meta.latency_ms} ms`}{gem?.configured === false && ' · no Gemini key'}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { chat } = useApp()
  const { data: cfg } = useFetch('/chat/config')
  const [open, setOpen] = useState(false)
  const last = [...chat.messages].reverse().find((m) => m.role === 'agent' && m.meta)
  const gem = cfg?.gemini

  return (
    <div className="flex h-[calc(100dvh-7.5rem)] min-h-[34rem] flex-col">
      <PageHeader title="Assistant" description="Ask about the plant in plain language, or tell it to run a simulation. Anything that changes state asks you to confirm first." />
      {gem && !gem.configured && (
        <div className="mb-3 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[13px] text-t-warning">
          No Gemini API key was found, so answers come from the offline Micro LM (read-only). Add <code className="mono">GEMINI_API_KEY</code> to <code className="mono">backend/.env</code> and restart to enable tool calling and actions.
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-12 gap-4">
        <Panel className="col-span-12 min-h-0 xl:col-span-8" bodyClass="flex min-h-0 flex-col"><Chat /></Panel>
        <div className="col-span-12 flex min-h-0 flex-col gap-4 xl:col-span-4">
          <Panel className="shrink-0" flush>
            <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left" aria-expanded={open}>
              <span className="panel-title">How the last answer was built</span>
              <ChevronDown size={15} className={cx('text-ink-muted transition-transform', open && 'rotate-180')} />
            </button>
            {open && <div className="border-t border-hairline px-4 py-4"><Provenance last={last} gem={gem} /></div>}
          </Panel>
          <AgentBus className="min-h-0 flex-1" max={10} title="Agent communication" bodyClass="min-h-0 overflow-y-auto" />
        </div>
      </div>
    </div>
  )
}
