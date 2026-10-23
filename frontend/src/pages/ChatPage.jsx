import Chat from '../components/Chat'
import { useApp } from '../ctx'
import { Badge, Panel } from '../ui'

export default function ChatPage() {
  const { chat } = useApp()
  const last = [...chat.messages].reverse().find((m) => m.role === 'agent' && m.meta)
  const meta = last?.meta
  return (
    <div className="grid h-[calc(100vh-170px)] grid-cols-12 gap-4">
      <Panel title="Space Supply Agent" className="col-span-12 xl:col-span-8"><Chat /></Panel>
      <Panel title="How the last answer was built" className="col-span-12 xl:col-span-4" bodyClass="overflow-y-auto">
        {!meta ? <p className="text-sm text-slate-400">Ask something to see the Micro LM's intent, entities and the agents that were called.</p> : (
          <div className="space-y-4 text-sm">
            <div><div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">1 · Micro LM intent</div><Badge tone="violet">{meta.intent} · {(meta.confidence * 100).toFixed(0)}%</Badge>{meta.fallback && <Badge tone="amber" className="ml-1">keyword fallback used</Badge>}</div>
            <div><div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">Top intents</div><ul className="space-y-1 text-xs">{(meta.top_intents || []).map((t, i) => <li key={i} className="flex justify-between"><span>{(t.intent || t[0] || '').replace?.(/_/g, ' ')}</span><span className="text-slate-400">{(((t.p ?? t.prob ?? t[1]) || 0) * 100).toFixed(0)}%</span></li>)}</ul></div>
            <div><div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">2 · Entities</div><div className="flex flex-wrap gap-1">{meta.entities.length ? meta.entities.map((e, i) => <Badge key={i}>{e.type}: {e.text}{e.id ? ` → ${e.id}` : ''}</Badge>) : <span className="text-xs text-slate-500">none</span>}</div></div>
            <div><div className="mb-1 text-[11px] uppercase tracking-wider text-slate-400">3 · Agents called</div><ul className="space-y-1 text-xs">{meta.agents_called.map((a, i) => <li key={i}><Badge tone="blue">{a.agent}</Badge> <span className="text-slate-300">{a.action}</span></li>)}</ul></div>
            <div className="text-xs text-slate-400">Wording: {meta.llm_used ? 'rewritten by Qwen (facts verified)' : 'deterministic template'} · {meta.latency_ms} ms</div>
          </div>)}
      </Panel>
    </div>
  )
}
