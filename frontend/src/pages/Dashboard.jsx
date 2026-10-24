import { AlertTriangle, ArrowRight, Info, OctagonAlert, Zap } from 'lucide-react'
import { CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import AgentBus from '../components/AgentBus'
import Chat from '../components/Chat'
import { LiveControls, LiveFeed } from '../components/Live'
import Rocket from '../components/Rocket'
import { useApp, useFetch } from '../ctx'
import { Badge, Panel, STAGE_COLORS, Spinner, nice, sevTone, statusTone } from '../ui'

const GROUPS = [
  ['available', 'Available', '#22c55e'], ['in_inspection', 'In Inspection', '#3b82f6'], ['in_assembly', 'In Assembly', '#f59e0b'],
  ['installed', 'Installed', '#14b8a6'], ['on_order', 'On Order', '#64748b'], ['rejected', 'Rejected', '#ef4444'], ['delayed', 'Delayed', '#a78bfa'],
]
const SevIcon = ({ s }) => s === 'CRITICAL' ? <OctagonAlert size={18} className="text-bad" /> : s === 'WARNING' ? <AlertTriangle size={18} className="text-warn" /> : <Info size={18} className="text-accent-soft" />

export default function Dashboard({ go, openComponent, openTask }) {
  const { data: d, loading } = useFetch('/dashboard', 8000)
  if (loading || !d) return <Spinner label="Loading mission data…" />
  const total = GROUPS.reduce((a, [k]) => a + d.component_status[k].units, 0)
  const pie = GROUPS.map(([k, label, color]) => ({ name: label, value: d.component_status[k].units, color })).filter((x) => x.value > 0)
  const startMs = new Date(d.now_iso).getTime() - d.now_hour * 3600e3
  const tick = (h) => new Date(startMs + h * 3600e3).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  const inv = d.inventory
  const tiles = [['Sufficient', inv.sufficient, '#22c55e', 'lots'], ['Low stock', inv.low, '#f59e0b', 'lots'], ['Critical', inv.critical, '#ef4444', 'lots'], ['On order', inv.on_order, '#3b82f6', 'lots']]

  return (
    <div className="grid grid-cols-12 gap-4">
      <Panel title="Launch vehicle overview" className="col-span-12 h-[330px] xl:col-span-8"
             right={<span className="text-xs text-slate-400">Projected launch-readiness review: <b className={d.launch.launch_readiness_late_hours ? 'text-amber-300' : 'text-green-300'}>{d.launch.launch_readiness}</b></span>}>
        <Rocket stages={d.stages} />
      </Panel>
      <Panel title="Space Supply Agent (LLM)" className="col-span-12 h-[330px] xl:col-span-4"><Chat compact /></Panel>

      <Panel title="Component status" className="col-span-12 md:col-span-6 xl:col-span-4 h-[300px]">
        <div className="flex h-full items-center gap-2">
          <div className="relative h-full w-1/2">
            <ResponsiveContainer><PieChart><Pie data={pie} dataKey="value" innerRadius="62%" outerRadius="92%" stroke="#0b1330" strokeWidth={2}>
              {pie.map((e) => <Cell key={e.name} fill={e.color} />)}</Pie><Tooltip contentStyle={{ background: '#101a3d', border: '1px solid #1c2b5a', borderRadius: 8 }} /></PieChart></ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center"><div className="text-2xl font-bold text-white">{total}</div><div className="text-xs text-slate-400">units</div></div>
          </div>
          <ul className="w-1/2 space-y-1.5 text-xs">{GROUPS.map(([k, label, color]) => (
            <li key={k} className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} /><span className="flex-1 text-slate-300">{label}</span>
              <span className="text-slate-100">{d.component_status[k].units}</span><span className="w-9 text-right text-slate-500">{Math.round((100 * d.component_status[k].units) / total)}%</span></li>))}</ul>
        </div>
      </Panel>

      <Panel title="Inventory status" className="col-span-12 md:col-span-6 xl:col-span-4 h-[300px]">
        <div className="grid h-full grid-cols-2 gap-3">{tiles.map(([label, v, c, unit]) => (
          <button key={label} onClick={() => go('inventory')} className="rounded-xl border border-line bg-space-900/60 p-4 text-left transition hover:border-accent">
            <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: c }}>{label}</div>
            <div className="mt-2 text-3xl font-bold text-white">{v}</div><div className="text-xs text-slate-500">{unit}</div></button>))}</div>
      </Panel>

      <Panel title="Today's schedule" className="col-span-12 xl:col-span-4 h-[300px]" right={<button className="text-xs text-accent-soft hover:underline" onClick={() => go('schedule')}>Open Gantt <ArrowRight size={11} className="inline" /></button>}>
        <div className="h-full overflow-y-auto"><table className="w-full"><thead><tr><th className="th">Task</th><th className="th">Name</th><th className="th">WS</th><th className="th">Start</th><th className="th">Status</th></tr></thead>
          <tbody>{d.todays_schedule.map((t) => (
            <tr key={t.id} onClick={() => openTask(t.id)} className="cursor-pointer border-t border-line/50 hover:bg-space-700/60">
              <td className="td !px-2 !py-1.5 text-xs">{t.id}</td><td className="td !px-2 !py-1.5 text-xs">{t.name}</td><td className="td !px-2 !py-1.5 text-xs">{t.workstation}</td>
              <td className="td !px-2 !py-1.5 text-xs">{t.time}</td><td className="td !px-2 !py-1.5 text-xs"><Badge tone={t.status === 'In Progress' ? 'cyan' : 'amber'}>{t.status}</Badge></td></tr>))}</tbody></table></div>
      </Panel>

      <Panel title="Alerts" className="col-span-12 md:col-span-6 xl:col-span-4 h-[300px]" right={<button className="text-xs text-accent-soft hover:underline" onClick={() => go('alerts')}>View all <ArrowRight size={11} className="inline" /></button>}>
        <ul className="h-full space-y-2 overflow-y-auto">{d.alerts.length === 0 && <li className="text-sm text-slate-400">No open alerts. All systems nominal.</li>}
          {d.alerts.map((a) => (
            <li key={a.id} className="flex gap-3 rounded-lg border border-line/70 bg-space-900/50 p-2.5"><SevIcon s={a.severity} />
              <div className="min-w-0 flex-1"><div className={`text-[11px] font-semibold uppercase ${a.severity === 'CRITICAL' ? 'text-red-300' : a.severity === 'WARNING' ? 'text-amber-300' : 'text-blue-300'}`}>{a.severity}</div>
                <div className="truncate text-sm text-slate-100" title={a.title}>{a.title}</div></div><div className="text-[11px] text-slate-500">{a.time.slice(7)}</div></li>))}</ul>
      </Panel>

      <Panel title="Assembly progress" className="col-span-12 md:col-span-6 xl:col-span-4 h-[300px]" right={<span className="text-[11px] text-slate-500">actual · projected after NOW</span>}>
        <ResponsiveContainer>
          <LineChart data={d.progress.points} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#1c2b5a" strokeDasharray="3 3" />
            <XAxis dataKey="hour" type="number" domain={['dataMin', 'dataMax']} tickFormatter={tick} tick={{ fill: '#94a3b8', fontSize: 10 }} tickCount={7} />
            <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <Tooltip labelFormatter={(h) => tick(h)} contentStyle={{ background: '#101a3d', border: '1px solid #1c2b5a', borderRadius: 8, fontSize: 12 }} />
            <ReferenceLine x={d.progress.now} stroke="#22d3ee" strokeDasharray="4 3" label={{ value: 'NOW', fill: '#22d3ee', fontSize: 10, position: 'top' }} />
            {[1, 2, 3, 4].map((i) => <Line key={i} type="monotone" dataKey={`s${i}`} name={`Stage ${i}`} stroke={STAGE_COLORS[i]} strokeWidth={2} dot={false} />)}
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} />
          </LineChart>
        </ResponsiveContainer>
      </Panel>

      {/* the two live feeds sit side by side: what the plant is doing, and what the agents
          are saying to each other about it */}
      <Panel title="Live activity" className="col-span-12 h-[320px] xl:col-span-8" right={<LiveControls compact />}>
        <LiveFeed />
      </Panel>

      <AgentBus className="col-span-12 h-[320px] xl:col-span-4" max={14} bodyClass="overflow-y-auto" />

      <Panel title="Upcoming deliveries" className="col-span-12 h-[320px] xl:col-span-8" right={<button className="text-xs text-accent-soft hover:underline" onClick={() => go('inventory')}>View all <ArrowRight size={11} className="inline" /></button>}>
        <div className="h-full overflow-y-auto"><table className="w-full"><thead><tr><th className="th">ID</th><th className="th">Component</th><th className="th">ETA</th><th className="th">Supplier</th></tr></thead>
          <tbody>{d.deliveries.length === 0 && <tr><td colSpan={4} className="td text-sm text-slate-400">All deliveries received.</td></tr>}{d.deliveries.map((x) => (
            <tr key={x.id} onClick={() => openComponent(x.component_id)} className="cursor-pointer border-t border-line/50 hover:bg-space-700/60">
              <td className="td !px-2 !py-1.5 text-xs">{x.component_id}</td><td className="td !px-2 !py-1.5 text-xs">{x.component}</td>
              <td className="td !px-2 !py-1.5 text-xs">{x.eta}{x.delay_hours > 0 && <Badge tone="red" className="ml-1">+{x.delay_hours}h</Badge>}</td>
              <td className="td !px-2 !py-1.5 text-xs text-slate-400">{x.supplier.split(' ').slice(0, 2).join(' ')}</td></tr>))}</tbody></table></div>
      </Panel>
    </div>
  )
}
