import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { get, post, stream } from './api'
import { AppCtx } from './ctx'
import { ComponentDrawer, TaskDrawer } from './components/Drawers'
import Layout from './components/Layout'
import ScenarioPanel from './components/ScenarioPanel'
import { ToastProvider } from './components/Toast'
import Dashboard from './pages/Dashboard'
import Components from './pages/Components'
import Inventory from './pages/Inventory'
import Schedule from './pages/Schedule'
import Tracking from './pages/Tracking'
import Alerts from './pages/Alerts'
import Reports from './pages/Reports'
import Agents from './pages/Agents'
import ChatPage from './pages/ChatPage'

const VIEWS = { dashboard: Dashboard, components: Components, inventory: Inventory, schedule: Schedule, tracking: Tracking, alerts: Alerts, agents: Agents, chat: ChatPage, reports: Reports }
const pageFromHash = () => {
  const h = window.location.hash.replace(/^#\/?/, '').split('?')[0]
  return VIEWS[h] ? h : 'dashboard'
}
const DEFAULTS = ['Where is the fuel pump?', 'Show today\'s schedule', 'Why was Engine Assembly delayed?', 'What are the critical shortages?']
const WELCOME = {
  role: 'agent',
  text: 'Hello! I\'m the **Space Supply Agent**. Ask me about components, inventory, the schedule, delays or alerts — I can also **run simulations** and **drive this dashboard** for you. Try “show me alerts for stage 3” or “delay CMP-021 by 24 hours”.',
}

/** Fold one streamed event into the assistant message being built. */
function applyEvent(msg, ev) {
  switch (ev.type) {
    case 'start':
      return { ...msg, microlm: ev.microlm }
    case 'token':
      return { ...msg, text: msg.text + ev.text }
    case 'tool_call':
      return { ...msg, tools: [...msg.tools, { tool: ev.tool, args: ev.args, running: true }] }
    case 'tool_result': {
      const tools = [...msg.tools]
      for (let i = tools.length - 1; i >= 0; i -= 1) {
        if (tools[i].tool === ev.tool && tools[i].running) {
          tools[i] = { ...tools[i], running: false, ms: ev.ms, ok: ev.ok, error: ev.error }
          break
        }
      }
      return { ...msg, tools }
    }
    case 'block':
      return { ...msg, blocks: [...msg.blocks, ev.block] }
    case 'pending':
      return { ...msg, pending: ev.action }
    case 'note':
      return { ...msg, notes: [...msg.notes, ev.text] }
    case 'fallback':
      return { ...msg, fallback: ev.message, text: '' }
    case 'replace':
      return { ...msg, text: ev.text, ungrounded: ev.ungrounded }
    case 'done':
      return { ...msg, streaming: false, text: ev.answer || msg.text, meta: ev }
    default:
      return msg
  }
}

function Shell() {
  const [page, setPage] = useState(pageFromHash)
  const [tick, setTick] = useState(0)
  const [comp, setComp] = useState(null)
  const [task, setTask] = useState(null)
  const [sim, setSim] = useState(false)
  const [messages, setMessages] = useState([WELCOME])
  const [busy, setBusy] = useState(false)
  const [filters, setFilters] = useState({})     // chat-driven page filters
  const [confirmActions, setConfirmActions] = useState(true)
  const session = useRef(`ui-${Math.random().toString(36).slice(2, 10)}`)
  const bump = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => { get('/chat/config').then((r) => setConfirmActions(r.confirm_actions)).catch(() => {}) }, [])

  // the URL hash is the router: deep links and the Back button work
  useEffect(() => {
    const onHash = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  const go = useCallback((p, f) => {
    if (window.location.hash !== `#/${p}`) window.location.hash = `/${p}`
    setPage(p)
    if (f && Object.keys(f).length) setFilters((prev) => ({ ...prev, ...f }))
  }, [])

  /** Run a UI command the assistant returned from a tool. */
  const applyUi = useCallback((cmd) => {
    if (!cmd) return
    if (cmd.action === 'navigate' && cmd.page) go(cmd.page, cmd.filters)
    else if (cmd.filters) setFilters((prev) => ({ ...prev, ...cmd.filters }))
    if (cmd.component_id) setComp(cmd.component_id)
    if (cmd.task_id) setTask(cmd.task_id)
  }, [go])

  // ---- live mode (clock + event feed driven by the backend simulator)
  const [liveState, setLiveState] = useState({ running: false, speed: 4, chaos: true })
  const [feed, setFeed] = useState([])
  const lastId = useRef(0)
  const lastBump = useRef(0)
  useEffect(() => {
    let alive = true
    const poll = async () => {
      try {
        const r = await get(`/live?since=${lastId.current}`)
        if (!alive) return
        setLiveState({ running: r.running, speed: r.speed, chaos: r.chaos })
        if (r.last_id < lastId.current) { lastId.current = 0; setFeed([]) }   // backend was reset
        if (r.feed.length) {
          lastId.current = r.feed[r.feed.length - 1].id
          setFeed((f) => [...f, ...r.feed].slice(-300))
          const now = Date.now()
          if (now - lastBump.current > 1500) { lastBump.current = now; bump() }
        }
      } catch { /* backend restarting */ }
    }
    poll()
    const id = setInterval(poll, liveState.running ? 1000 : 3000)
    return () => { alive = false; clearInterval(id) }
  }, [bump, liveState.running])

  const configure = useCallback(async (patch) => {
    setLiveState((s) => ({ ...s, ...patch }))          // optimistic
    try { const r = await post('/live', patch); setLiveState({ running: r.running, speed: r.speed, chaos: r.chaos }) } catch { /* ignore */ }
  }, [])
  const live = useMemo(() => ({
    ...liveState, feed,
    setRunning: (v) => configure({ running: v }),
    setSpeed: (v) => configure({ speed: v }),
    setChaos: (v) => configure({ chaos: v }),
    reset: async () => { await post('/reset'); lastId.current = 0; setFeed([]); setLiveState((s) => ({ ...s, running: false })); bump() },
  }), [liveState, feed, configure, bump])

  const send = useCallback(async (text) => {
    const id = `m${Date.now()}`
    const blank = { role: 'agent', id, text: '', streaming: true, tools: [], blocks: [], notes: [] }
    setMessages((m) => [...m, { role: 'user', text }, blank])
    setBusy(true)
    const patch = (ev) => setMessages((m) => m.map((msg) => (msg.id === id ? applyEvent(msg, ev) : msg)))
    try {
      await stream('/chat/stream', { message: text, session_id: session.current }, (ev) => {
        patch(ev)
        if (ev.type === 'ui') applyUi(ev.command)
        if (ev.type === 'done') bump()
      })
      // the stream ended without a done frame (server restart, dropped connection)
      setMessages((m) => m.map((msg) => (msg.id === id && msg.streaming
        ? { ...msg, streaming: false, text: msg.text || 'The connection dropped before I could answer. Please try again.' }
        : msg)))
    } catch (e) {
      setMessages((m) => m.map((msg) => (msg.id === id
        ? { ...msg, streaming: false, text: `Sorry, something went wrong: ${e.message}` } : msg)))
    } finally { setBusy(false) }
  }, [bump, applyUi])

  /** Confirm or cancel a simulation action the assistant proposed. */
  const resolveAction = useCallback(async (msgId, action, approve) => {
    setMessages((m) => m.map((msg) => (msg.id === msgId ? { ...msg, pending: { ...action, busy: true } } : msg)))
    try {
      const r = await post('/chat/confirm', { action_id: action.id, approve, session_id: session.current })
      setMessages((m) => [
        ...m.map((msg) => (msg.id === msgId ? { ...msg, pending: null, resolved: approve ? 'approved' : 'cancelled' } : msg)),
        { role: 'agent', id: `a${Date.now()}`, text: r.answer, tools: r.tools_called || [], blocks: r.blocks || [], notes: [], meta: r },
      ])
      ;(r.ui_commands || []).forEach(applyUi)
      bump()
    } catch (e) {
      setMessages((m) => m.map((msg) => (msg.id === msgId
        ? { ...msg, pending: null, resolved: 'failed', text: `${msg.text}\n\n(${e.message})` } : msg)))
    }
  }, [bump, applyUi])

  const newChat = useCallback(async () => {
    const old = session.current
    session.current = `ui-${Math.random().toString(36).slice(2, 10)}`
    setMessages([WELCOME])
    try { await post(`/chat/new?session_id=${encodeURIComponent(old)}`) } catch { /* ignore */ }
  }, [])

  const setConfirm = useCallback(async (v) => {
    setConfirmActions(v)
    try { const r = await post('/chat/config', { confirm: v }); setConfirmActions(r.confirm_actions) } catch { /* ignore */ }
  }, [])

  const chat = useMemo(() => ({
    messages, busy, send, defaults: DEFAULTS, resolveAction, newChat,
    confirmActions, setConfirm, sessionId: session.current,
  }), [messages, busy, send, resolveAction, newChat, confirmActions, setConfirm])

  const ctx = useMemo(() => ({
    tick, bump, live, chat, page, go, filters, setFilters,
    openComponent: setComp, openTask: setTask,
  }), [tick, bump, live, chat, page, go, filters])

  const View = VIEWS[page] || Dashboard
  return (
    <AppCtx.Provider value={ctx}>
      <Layout page={page} go={go} openSim={() => setSim(true)}>
        <View go={go} openComponent={setComp} openTask={setTask} />
      </Layout>
      <ComponentDrawer id={comp} onClose={() => setComp(null)} onTask={(t) => { setComp(null); setTask(t) }} />
      <TaskDrawer id={task} onClose={() => setTask(null)} onComponent={(c) => { setTask(null); setComp(c) }} />
      <ScenarioPanel open={sim} onClose={() => setSim(false)} onDone={bump} />
    </AppCtx.Provider>
  )
}

export default function App() { return <ToastProvider><Shell /></ToastProvider> }
