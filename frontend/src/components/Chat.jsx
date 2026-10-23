import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Bot, Check, Cpu, Plus, Send, ShieldQuestion, Sparkles, User, Wrench, X, Zap } from 'lucide-react'
import { get } from '../api'
import { useApp } from '../ctx'
import { Badge, RichText } from '../ui'

const AGENT_TONE = { 'Language Agent': 'violet', 'Tracking Agent': 'cyan', 'Supply Agent': 'amber', 'Scheduling Agent': 'blue', 'Monitoring Agent': 'red' }
const WRITE_TOOLS = new Set(['delay_delivery', 'reject_component', 'workstation_down', 'replan_schedule', 'advance_time'])
const prettyTool = (t = '') => t.replace(/_/g, ' ')

/** Tool calls the supervisor made, shown as they happen. */
function ToolChips({ tools }) {
  if (!tools?.length) return null
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {tools.map((t, i) => (
        <span key={i} title={t.error || (t.args ? JSON.stringify(t.args) : '')}
              className={`chip inline-flex items-center gap-1 ring-1 ${
                t.running ? 'bg-accent/10 text-blue-300 ring-accent/30'
                  : t.ok === false ? 'bg-bad/15 text-red-300 ring-bad/30'
                    : WRITE_TOOLS.has(t.tool) ? 'bg-warn/15 text-amber-300 ring-warn/30'
                      : 'bg-space-600/60 text-slate-300 ring-line'}`}>
          {t.running ? <Sparkles size={11} className="animate-pulse" /> : <Wrench size={11} />}
          {prettyTool(t.tool)}
          {!t.running && t.ms != null && <span className="text-slate-500">{t.ms}ms</span>}
        </span>
      ))}
    </div>
  )
}

/** Small tables / cards a tool asked the chat to render inline. */
function Block({ block }) {
  if (block.type === 'table') {
    return (
      <div className="mt-2 overflow-auto rounded-lg border border-line">
        {block.title && <div className="border-b border-line bg-space-900/60 px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{block.title}</div>}
        <table className="w-full">
          <thead className="bg-space-700"><tr>{block.columns.map((c) => <th key={c} className="th">{c}</th>)}</tr></thead>
          <tbody>
            {block.rows.map((r, i) => (
              <tr key={i} className="border-t border-line/50 hover:bg-space-700/60">
                {r.map((cell, j) => <td key={j} className="td">{String(cell ?? '-')}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (block.type === 'card') {
    return (
      <div className="mt-2 rounded-lg border border-line bg-space-900/60 p-3">
        {block.title && <div className="mb-1 text-xs font-semibold text-white">{block.title}</div>}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          {Object.entries(block.fields || {}).map(([k, v]) => (
            <div key={k}><span className="text-slate-500">{k}: </span><span className="text-slate-200">{String(v)}</span></div>
          ))}
        </div>
      </div>
    )
  }
  return null
}

/** Confirm / Cancel for a simulation action the assistant wants to run. */
function ConfirmCard({ action, onResolve }) {
  return (
    <div className="mt-2 rounded-lg border border-warn/40 bg-warn/10 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-amber-200">
        <ShieldQuestion size={14} /> Confirm this change
      </div>
      <div className="mb-2.5 text-[12px] leading-relaxed text-slate-200">{action.summary}</div>
      <div className="flex gap-2">
        <button className="btn btn-primary !py-1 !text-[11px]" disabled={action.busy}
                onClick={() => onResolve(action, true)}>
          <Check size={13} />{action.busy ? 'Running…' : 'Confirm'}
        </button>
        <button className="btn !py-1 !text-[11px]" disabled={action.busy} onClick={() => onResolve(action, false)}>
          <X size={13} />Cancel
        </button>
      </div>
    </div>
  )
}

function SourceBadges({ m, compact }) {
  const meta = m.meta
  if (!meta) return null
  const src = meta.source
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-line/70 pt-2">
      {src === 'gemini' && <Badge tone="green">{meta.model || 'Gemini'}</Badge>}
      {src === 'microlm' && <Badge tone="amber">offline Micro LM</Badge>}
      {src === 'action' && <Badge tone="blue">action applied</Badge>}
      {src === 'error' && <Badge tone="red">error</Badge>}
      {meta.grounded === false && <Badge tone="red">answer rewritten</Badge>}
      {!compact && m.microlm?.intent && (
        <Badge tone="violet">Micro LM: {String(m.microlm.intent).replace(/_/g, ' ').toLowerCase()}
          {m.microlm.confidence != null && ` · ${(m.microlm.confidence * 100).toFixed(0)}%`}</Badge>
      )}
      {!compact && meta.latency_ms != null && <span className="text-[10px] text-slate-500">{meta.latency_ms} ms</span>}
      {/* the offline fallback still reports which specialist agents answered */}
      {src === 'microlm' && (meta.tools_called || []).map((a, i) => (
        <Badge key={i} tone={AGENT_TONE[a.tool] || 'slate'}>{String(a.tool).replace(' Agent', '')}</Badge>
      ))}
    </div>
  )
}

function Message({ m, compact, onResolve }) {
  const agent = m.role === 'agent'
  return (
    <div className={`flex gap-2 ${agent ? '' : 'flex-row-reverse'}`}>
      <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${agent ? 'bg-space-500 text-accent-cyan' : 'bg-accent text-white'}`}>
        {agent ? <Bot size={15} /> : <User size={15} />}
      </div>
      <div className={`max-w-[88%] rounded-xl px-3 py-2 ${agent ? 'bg-space-700 text-slate-100' : 'bg-accent text-white'}`}>
        {agent ? (
          <>
            <ToolChips tools={m.tools} />
            {m.notes?.map((n, i) => (
              <div key={i} className="mb-1.5 flex items-center gap-1.5 text-[11px] text-amber-300"><Zap size={11} />{n}</div>
            ))}
            {m.fallback && (
              <div className="mb-2 flex items-start gap-1.5 rounded-lg border border-warn/40 bg-warn/10 px-2.5 py-1.5 text-[11px] text-amber-200">
                <Cpu size={12} className="mt-0.5 shrink-0" />{m.fallback}
              </div>
            )}
            {m.text ? <RichText text={m.text} /> : m.streaming
              ? <div className="flex items-center gap-2 text-xs text-slate-400"><Sparkles size={13} className="animate-pulse" />thinking…</div>
              : null}
            {m.streaming && m.text && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-accent-cyan align-middle" />}
            {m.ungrounded?.length > 0 && (
              <div className="mt-2 flex items-start gap-1.5 rounded-lg border border-bad/40 bg-bad/10 px-2.5 py-1.5 text-[11px] text-red-200">
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                Dropped the first draft: it used {m.ungrounded.join(', ')}, which no agent returned.
              </div>
            )}
            {m.blocks?.map((b, i) => <Block key={i} block={b} />)}
            {m.pending && <ConfirmCard action={m.pending} onResolve={(a, ok) => onResolve(m.id, a, ok)} />}
            {m.resolved === 'cancelled' && <div className="mt-2 text-[11px] text-slate-400">Cancelled – nothing was changed.</div>}
            <SourceBadges m={m} compact={compact} />
          </>
        ) : <div className="text-sm">{m.text}</div>}
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
      {!compact && (
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-line pb-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-400" title="When off, the assistant runs simulation actions straight away (handy for a live demo).">
            <input type="checkbox" className="accent-accent" checked={chat.confirmActions}
                   onChange={(e) => chat.setConfirm(e.target.checked)} />
            Ask before changing the simulation
          </label>
          <button className="btn !py-1 !text-[11px]" onClick={chat.newChat}><Plus size={12} />New chat</button>
        </div>
      )}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {chat.messages.map((m, i) => <Message key={m.id || i} m={m} compact={compact} onResolve={chat.resolveAction} />)}
        <div ref={end} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {chips.slice(0, compact ? 3 : 5).map((s) => (
          <button key={s} onClick={() => (auto.length ? setText(s + ' ') : submit(s))}
                  className="rounded-full border border-line bg-space-700 px-2.5 py-1 text-[11px] text-slate-300 hover:border-accent hover:text-white">{s}</button>
        ))}
      </div>
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); submit() }}>
        <input className="input flex-1" placeholder="Ask, or tell me to run something…" value={text}
               onChange={(e) => setText(e.target.value)} maxLength={500} />
        <button className="btn btn-primary" disabled={chat.busy || !text.trim()} aria-label="Send"><Send size={15} /></button>
      </form>
    </div>
  )
}
