import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Boxes, CalendarClock, Languages, MessageSquareShare, ShieldAlert, Truck } from 'lucide-react'
import { get } from '../api'
import { useApp } from '../ctx'
import { Badge, Panel } from '../ui'

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
export default function AgentBus({ className = '', max = 40, title = 'Agent communication (message bus)', bodyClass = 'max-h-96 overflow-y-auto' }) {
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
  const stripe = (id) => ['#3b82f6', '#22d3ee', '#a78bfa', '#f59e0b', '#22c55e'][convs.indexOf(id) % 5]

  return (
    <Panel title={title} className={className} data-testid="agent-bus" bodyClass={bodyClass}
           right={<Badge tone="slate">{messages.length} message(s)</Badge>}>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">
          No messages yet. The agents publish here when something happens — trigger a scenario, start live
          mode, or ask the assistant to delay a delivery.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((msg) => {
            const I = AGENT_ICON[msg.sender] || MessageSquareShare
            return (
              <li key={msg.id} data-testid="agent-bus-item" data-topic={msg.topic} className="flex gap-2.5 rounded-lg border border-line bg-space-900/60 p-2.5"
                  style={{ borderLeft: `3px solid ${stripe(msg.correlation_id)}` }}>
                <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-space-600 text-accent-soft">
                  <I size={15} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    <span className="font-semibold text-white">{short(msg.sender)}</span>
                    <ArrowRight size={11} className="text-slate-500" />
                    <span className="text-slate-400">{msg.recipient === '*' ? 'all agents' : short(msg.recipient)}</span>
                    <Badge tone={TOPIC_TONE[msg.topic] || 'slate'}>{msg.topic}</Badge>
                    <span className="ml-auto text-slate-500">{msg.time}</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-300">{msg.summary}</div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}
