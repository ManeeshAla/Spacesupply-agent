import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Boxes, CalendarClock, Languages, MessageSquareShare, ShieldAlert, Truck } from 'lucide-react'
import { get } from '../api'
import { useApp } from '../ctx'
import { Panel } from '../ui'

const AGENT_ICON = { 'Tracking Agent': Boxes, 'Supply Agent': Truck, 'Scheduling Agent': CalendarClock, 'Monitoring Agent': ShieldAlert, 'Language Agent': Languages }
const TOPIC_TONE = {
  'supplier.delay': 'amber', 'component.rejected': 'red', 'workstation.down': 'red',
  'replan.requested': 'violet', 'schedule.replanned': 'blue', 'alerts.scanned': 'cyan',
  'time.advanced': 'slate',
}
const short = (a = '') => a.replace(' Agent', '')

/**
 * Live view of the message bus: what each agent published, and which conversation
 * (correlation id) it belongs to. Messages of one trigger share a colour stripe.
 */
export default function AgentBus({ className = '', max = 40, title = 'Agent communication (message bus)', bodyClass = 'max-h-96 overflow-y-auto', height }) {
  const { tick } = useApp()
  const [messages, setMessages] = useState([])
  const since = useRef(0)

  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await get(`/bus?since=${since.current}`)
        if (!alive) return
        if (r.last_id < since.current) { since.current = 0; setMessages([]) }   // backend reset
        if (r.messages.length) {
          since.current = r.messages[r.messages.length - 1].id
          setMessages((m) => [...m, ...r.messages].slice(-300))
        }
      } catch { /* backend restarting */ }
    }
    poll()
    const id = setInterval(poll, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [tick])

  // Newest conversation first, but inside one conversation oldest message first, so a cause
  // (supplier.delay) reads above its effects (schedule.replanned, alerts.scanned).
  const order = []
  const byConv = {}
  for (const m of messages) {
    if (!byConv[m.correlation_id]) { byConv[m.correlation_id] = []; order.push(m.correlation_id) }
    byConv[m.correlation_id].push(m)
  }
  const rows = order.reverse().flatMap((id) => byConv[id]).slice(0, max)
  // one colour per conversation, so a delay and its re-plan and alerts line up visually
  const convs = [...new Set(rows.map((r) => r.correlation_id))]
  const stripe = (id) => ['rgb(var(--accent))', 'rgb(var(--aqua))', 'rgb(var(--violet))', 'rgb(var(--warning))', 'rgb(var(--ink-muted))'][convs.indexOf(id) % 5]

  return (
    <Panel title={title} subtitle="Agents talking to each other" className={className} data-testid="agent-bus" bodyClass={bodyClass} height={height}
           right={<span className="text-xs tabular text-ink-muted">{messages.length} message{messages.length === 1 ? '' : 's'}</span>}>
      {rows.length === 0 ? (
        <div className="flex h-full flex-col items-center justify-center gap-1.5 px-4 text-center">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-ink-muted"><MessageSquareShare size={16} /></div>
          <p className="text-sm font-medium text-ink">No messages yet</p>
          <p className="max-w-xs text-[13px] text-ink-3">Agents publish here when something happens. Start live mode or trigger a scenario.</p>
        </div>
      ) : (
        <ul>
          {rows.map((msg) => {
            const I = AGENT_ICON[msg.sender] || MessageSquareShare
            return (
              <li key={msg.id} data-testid="agent-bus-item" data-topic={msg.topic}
                  className="flex gap-3 border-b border-hairline/60 py-2.5 pl-3 last:border-0" style={{ borderLeft: `2px solid ${stripe(msg.correlation_id)}` }}>
                <I size={15} className="mt-0.5 shrink-0 text-ink-muted" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                    <span className="font-medium text-ink">{short(msg.sender)}</span>
                    <ArrowRight size={11} className="text-ink-muted" />
                    <span className="text-ink-3">{msg.recipient === '*' ? 'all agents' : short(msg.recipient)}</span>
                    <span className="mono rounded bg-surface-2 px-1.5 py-px text-[11px] text-ink-2">{msg.topic}</span>
                    <span className="ml-auto tabular text-ink-muted">{msg.time}</span>
                  </div>
                  <div className="mt-1 text-[13px] leading-snug text-ink-2">{msg.summary}</div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
