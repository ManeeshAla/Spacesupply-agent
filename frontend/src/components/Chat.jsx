import { useEffect, useRef, useState } from 'react'
import { Bot, Send, Sparkles, User } from 'lucide-react'
import { get } from '../api'
import { useApp } from '../ctx'
import { Badge, RichText } from '../ui'

const AGENT_TONE = { 'Language Agent': 'violet', 'Tracking Agent': 'cyan', 'Supply Agent': 'amber', 'Scheduling Agent': 'blue', 'Monitoring Agent': 'red' }

function Message({ m, compact }) {
  const agent = m.role === 'agent'
  return (
    <div className={`flex gap-2 ${agent ? '' : 'flex-row-reverse'}`}>
      <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${agent ? 'bg-space-500 text-accent-cyan' : 'bg-accent text-white'}`}>
        {agent ? <Bot size={15} /> : <User size={15} />}
      </div>
      <div className={`max-w-[88%] rounded-xl px-3 py-2 ${agent ? 'bg-space-700 text-slate-100' : 'bg-accent text-white'}`}>
        {agent ? <RichText text={m.text} /> : <div className="text-sm">{m.text}</div>}
        {agent && m.meta && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-line/70 pt-2">
            {!compact && (
              <>
                <Badge tone="violet">{m.meta.intent.replace(/_/g, ' ')} · {(m.meta.confidence * 100).toFixed(0)}%</Badge>
                {m.meta.fallback && <Badge tone="amber">keyword fallback</Badge>}
                {m.meta.entities.map((e, i) => <Badge key={i} tone="slate">{e.type}: {e.text}</Badge>)}
              </>
            )}
            {m.meta.agents_called.map((a, i) => (
              <span key={i} title={a.action}><Badge tone={AGENT_TONE[a.agent] || 'slate'}>{a.agent.replace(' Agent', '')}</Badge></span>
            ))}
            {m.meta.llm_used && <Badge tone="green">Qwen</Badge>}
          </div>
        )}
      </div>
    </div>
  )
}

export default function Chat({ compact = false }) {
  const { chat } = useApp()
  const [text, setText] = useState('')
  const [auto, setAuto] = useState([])
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [chat.messages, chat.busy])

  useEffect(() => {  // Micro-LM next-word auto-complete
    if (!text.trim()) { setAuto([]); return }
    const id = setTimeout(() => get(`/chat/suggest?q=${encodeURIComponent(text)}`).then((r) => setAuto(r.suggestions)).catch(() => setAuto([])), 160)
    return () => clearTimeout(id)
  }, [text])

  const submit = (t = text) => { if (!t.trim() || chat.busy) return; chat.send(t.trim()); setText(''); setAuto([]) }
  const last = [...chat.messages].reverse().find((m) => m.role === 'agent')
  const chips = auto.length ? auto : last?.meta?.suggestions?.length ? last.meta.suggestions : chat.defaults

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {chat.messages.map((m, i) => <Message key={i} m={m} compact={compact} />)}
        {chat.busy && <div className="flex items-center gap-2 pl-9 text-xs text-slate-400"><Sparkles size={13} className="animate-pulse" /> agents are working…</div>}
        <div ref={end} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {chips.slice(0, compact ? 3 : 5).map((s) => (
          <button key={s} onClick={() => (auto.length ? setText(s + ' ') : submit(s))}
                  className="rounded-full border border-line bg-space-700 px-2.5 py-1 text-[11px] text-slate-300 hover:border-accent hover:text-white">{s}</button>
        ))}
      </div>
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <input className="input flex-1" placeholder="Type your query…" value={text} onChange={(e) => setText(e.target.value)} maxLength={300} />
        <button className="btn btn-primary" disabled={chat.busy || !text.trim()} aria-label="Send"><Send size={15} /></button>
      </form>
    </div>
  )
}
