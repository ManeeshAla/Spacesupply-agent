import AgentBus from '../components/AgentBus'
import Chat from '../components/Chat'
import { useApp, useFetch } from '../ctx'
import { Badge, Panel } from '../ui'

const prettyTool = (t = '') => t.replace(/_/g, ' ')

export default function ChatPage() {
  const { chat } = useApp()
  const { data: cfg } = useFetch('/chat/config')
  const last = [...chat.messages].reverse().find((m) => m.role === 'agent' && m.meta)
  const meta = last?.meta
  const gem = cfg?.gemini

  return (
    <div className="grid h-[calc(100vh-170px)] grid-cols-12 gap-4">
      <Panel title="Space Supply Agent" className="col-span-12 xl:col-span-8"><Chat /></Panel>

      <div className="col-span-12 flex min-h-0 flex-col gap-4 xl:col-span-4">
        <Panel title="How the last answer was built" bodyClass="overflow-y-auto">
          {!gem?.configured && (
            <div className="mb-3 rounded-lg border border-warn/40 bg-warn/10 px-2.5 py-2 text-[11px] text-amber-200">
              No Gemini API key found, so the assistant is running on the offline Micro LM only (read-only
              answers). Add <code className="text-amber-100">GEMINI_API_KEY</code> to <code className="text-amber-100">backend/.env</code> and restart to enable
              tool calling and actions.
            </div>
          )}
          {!meta ? (
            <p className="text-sm text-slate-400">Ask something to see the tools that were called and how the answer was checked.</p>
          ) : (
            <div className="space-y-4 text-sm">
              <div>
                <div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">1 · Micro LM hint (local)</div>
                {last.microlm?.intent ? (
                  <>
                    <Badge tone="violet">{String(last.microlm.intent).replace(/_/g, ' ')}
                      {last.microlm.confidence != null && ` · ${(last.microlm.confidence * 100).toFixed(0)}%`}</Badge>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {(last.microlm.entities || []).map((e, i) => <Badge key={i}>{e.type}: {e.text}</Badge>)}
                    </div>
                  </>
                ) : <span className="text-xs text-slate-500">not recorded</span>}
              </div>

              <div>
                <div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">2 · Tools called</div>
                {meta.tools_called?.length ? (
                  <ul className="space-y-1 text-xs">
                    {meta.tools_called.map((t, i) => (
                      <li key={i} className="flex items-start justify-between gap-2">
                        <span><Badge tone={t.ok === false ? 'red' : 'blue'}>{prettyTool(t.tool)}</Badge>
                          {t.args && Object.keys(t.args).length > 0 && (
                            <span className="ml-1 text-slate-400">{JSON.stringify(t.args)}</span>
                          )}</span>
                        {t.ms != null && <span className="shrink-0 text-slate-500">{t.ms} ms</span>}
                      </li>
                    ))}
                  </ul>
                ) : <span className="text-xs text-slate-500">none – answered without plant data</span>}
              </div>

              <div>
                <div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">3 · Grounding check</div>
                {meta.grounded === false
                  ? <Badge tone="red">failed – draft replaced with raw tool output</Badge>
                  : <Badge tone="green">passed – every id and number came from a tool</Badge>}
              </div>

              <div className="text-xs text-slate-400">
                Answered by {meta.source === 'gemini' ? (meta.model || 'Gemini')
                  : meta.source === 'microlm' ? 'the offline Micro LM + templates'
                    : meta.source === 'action' ? 'a confirmed action (deterministic summary)' : meta.source}
                {meta.latency_ms != null && ` · ${meta.latency_ms} ms`}
              </div>
            </div>
          )}
        </Panel>

        <AgentBus className="min-h-0 flex-1" max={12} />
      </div>
    </div>
  )
}
