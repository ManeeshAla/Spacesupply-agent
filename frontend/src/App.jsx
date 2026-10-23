import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, BarChart3, Bell, Bot, Boxes, CalendarClock, Gauge, MessageSquare, Package, Rocket as RocketIcon, Route, Zap } from 'lucide-react'
import { get, post } from './api'
import { AppCtx, useFetch } from './ctx'
import { ComponentDrawer, TaskDrawer } from './components/Drawers'
import ScenarioPanel from './components/ScenarioPanel'
import { LiveControls, LiveDot } from './components/Live'
import Dashboard from './pages/Dashboard'
import Components from './pages/Components'
import Inventory from './pages/Inventory'
import Schedule from './pages/Schedule'
import Tracking from './pages/Tracking'
import Alerts from './pages/Alerts'
import Reports from './pages/Reports'
import Agents from './pages/Agents'
import ChatPage from './pages/ChatPage'

const NAV = [
  ['dashboard', 'Dashboard', Gauge], ['components', 'Components', Boxes], ['inventory', 'Inventory', Package], ['schedule', 'Schedule', CalendarClock],
  ['tracking', 'Tracking', Route], ['alerts', 'Alerts', Bell], ['agents', 'Agents', Activity], ['chat', 'AI Assistant', MessageSquare], ['reports', 'Reports', BarChart3],
]
const DEFAULTS = ['Where is the fuel pump?', 'Show today\'s schedule', 'Why was Engine Assembly delayed?', 'What are the critical shortages?']
const WELCOME = { role: 'agent', text: 'Hello! I\'m the **Space Supply Agent**. Ask about components, inventory, the schedule, delays or alerts — or type “help”.' }

function Shell() {
  const [page, setPage] = useState('dashboard')
  const [tick, setTick] = useState(0)
  const [comp, setComp] = useState(null)
  const [task, setTask] = useState(null)
  const [sim, setSim] = useState(false)
  const [messages, setMessages] = useState([WELCOME])
  const [busy, setBusy] = useState(false)
  const bump = useCallback(() => setTick((t) => t + 1), [])

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
    setMessages((m) => [...m, { role: 'user', text }]); setBusy(true)
    try {
      const r = await post('/chat', { message: text })
      setMessages((m) => [...m, { role: 'agent', text: r.answer, meta: r }]); bump()
    } catch (e) {
      setMessages((m) => [...m, { role: 'agent', text: `Sorry, something went wrong: ${e.message}` }])
    } finally { setBusy(false) }
  }, [bump])

  const ctx = useMemo(() => ({ tick, bump, live, chat: { messages, busy, send, defaults: DEFAULTS } }), [tick, bump, live, messages, busy, send])
  return (
    <AppCtx.Provider value={ctx}>
      <Layout page={page} setPage={setPage} openSim={() => setSim(true)} openComponent={setComp} openTask={setTask} />
      <ComponentDrawer id={comp} onClose={() => setComp(null)} onTask={(t) => { setComp(null); setTask(t) }} />
      <TaskDrawer id={task} onClose={() => setTask(null)} onComponent={(c) => { setTask(null); setComp(c) }} />
      <ScenarioPanel open={sim} onClose={() => setSim(false)} onDone={bump} />
    </AppCtx.Provider>
  )
}

function Kpi({ label, value, sub, tone = 'text-white' }) {
  return (
    <div className="panel min-w-[110px] flex-1 px-3 py-1.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`text-xl font-bold leading-tight ${tone}`}>{value}</div>
      {sub && <div className="text-[10px] text-slate-500">{sub}</div>}
    </div>
  )
}

function Layout({ page, setPage, openSim, openComponent, openTask }) {
  const { data: d } = useFetch('/dashboard', 8000)
  const k = d?.kpis
  const status = d?.system_status
  const sTone = status === 'OPERATIONAL' ? 'text-green-300' : status === 'ATTENTION' ? 'text-amber-300' : 'text-red-300'
  const props = { go: setPage, openComponent, openTask }
  const View = { dashboard: Dashboard, components: Components, inventory: Inventory, schedule: Schedule, tracking: Tracking, alerts: Alerts, agents: Agents, chat: ChatPage, reports: Reports }[page]
  return (
    <div className="flex h-full">
      <nav className="hidden w-56 shrink-0 flex-col border-r border-line bg-space-900/80 p-3 md:flex">
        <div className="mb-5 flex items-center gap-2 px-2 pt-1">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-white"><RocketIcon size={18} /></div>
          <div><div className="text-sm font-bold leading-tight text-white">SpaceSupply</div></div>
        </div>
        <ul className="space-y-1">{NAV.map(([id, label, I]) => (
          <li key={id}><button onClick={() => setPage(id)} className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${page === id ? 'bg-accent/20 text-white ring-1 ring-accent/40' : 'text-slate-400 hover:bg-space-700 hover:text-white'}`}>
            <I size={16} />{label}{id === 'alerts' && k?.pending_alerts > 0 && <span className="ml-auto rounded-full bg-bad px-1.5 text-[10px] font-bold text-white">{k.pending_alerts}</span>}</button></li>))}</ul>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-line px-5 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-base font-bold leading-tight text-white">Launch Vehicle Assembly Control</h1>
              <div className="flex items-center gap-2 text-[11px] text-slate-400"><LiveDot />Simulated plant time: {d ? new Date(d.now_iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '…'}</div>
            </div>
            <div className="flex items-center gap-2">
              <LiveControls />
              <button className="btn" onClick={openSim} title="Trigger a specific scenario yourself"><Zap size={14} />Scenario</button>
            </div>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <Kpi label="System" value={status || '…'} tone={sTone} />
            <Kpi label="Component units" value={k?.component_units ?? '–'} sub={k ? `${k.component_lots} lots` : ''} />
            <Kpi label="Ongoing tasks" value={k?.ongoing_tasks ?? '–'} />
            <Kpi label="Next 24 h" value={k?.planned_next_24h ?? '–'} sub="planned tasks" />
            <Kpi label="Open alerts" value={k?.pending_alerts ?? '–'} tone={k?.pending_alerts ? 'text-amber-300' : 'text-white'} />
            <Kpi label="Launch readiness" value={d?.launch?.launch_readiness ?? '–'} sub="projected" tone={d?.launch?.launch_readiness_late_hours ? 'text-amber-300' : 'text-white'} />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-4">{View && <View {...props} />}</main>
      </div>
    </div>
  )
}

export default function App() { return <Shell /> }
