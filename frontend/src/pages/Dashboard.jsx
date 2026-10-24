import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, Info, OctagonAlert, Package, Rocket, Timer } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import AgentBus from '../components/AgentBus'
import { LiveControls, LiveFeed } from '../components/Live'
import { ChartTooltip, axisProps, gridProps } from '../chartTheme'
import { useFetch } from '../ctx'
import { Badge, Bar, DataTable, EmptyState, PageHeader, Panel, STAGE_COLORS, Spinner, StatCard, cx, nice } from '../ui'

const SEV = {
  CRITICAL: [OctagonAlert, 'text-t-critical'], WARNING: [AlertTriangle, 'text-t-warning'], INFO: [Info, 'text-t-accent'],
}
const GROUPS = [
  ['available', 'Available'], ['in_inspection', 'In inspection'], ['in_assembly', 'In assembly'], ['installed', 'Installed'],
  ['on_order', 'On order'], ['rejected', 'Rejected'], ['delayed', 'Delayed'],
]
const GROUP_BAD = { rejected: 'rgb(var(--critical))', delayed: 'rgb(var(--warning))' }

const Link = ({ onClick, children }) => (
  <button onClick={onClick} className="inline-flex items-center gap-1 text-xs font-medium text-t-accent hover:underline">{children}<ArrowRight size={12} /></button>
)

export default function Dashboard({ go, openComponent, openTask }) {
  const { data: d, loading } = useFetch('/dashboard', 8000)
  if (loading || !d) return <Spinner label="Loading plant data…" />

  const late = d.launch.launch_readiness_late_hours
  const inv = d.inventory
  const critical = d.alerts.filter((a) => a.severity === 'CRITICAL').length
  const totalUnits = GROUPS.reduce((a, [k]) => a + d.component_status[k].units, 0) || 1
  const startMs = new Date(d.now_iso).getTime() - d.now_hour * 3600e3
  const day = (h) => new Date(startMs + h * 3600e3).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
  const pts = d.progress.points

  return (
    <div className="space-y-5">
      <PageHeader title="Plant overview" description="Live status of the launch-vehicle assembly line: schedule health, supply, and what the agents are doing about it." />

      {/* headline */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <StatCard label="Launch readiness review" icon={Rocket} value={d.launch.launch_readiness}
                  tone={late ? 'bad' : 'good'} sub={late ? `${late} h behind its deadline` : 'On schedule'} onClick={() => go('schedule')} />
        <StatCard label="Open alerts" icon={AlertTriangle} value={d.kpis.pending_alerts} tone={critical ? 'bad' : d.kpis.pending_alerts ? 'warn' : 'good'}
                  sub={critical ? `${critical} critical` : d.kpis.pending_alerts ? 'None critical' : 'All clear'} onClick={() => go('alerts')} />
        <StatCard label="Tasks running" icon={Timer} value={d.kpis.ongoing_tasks} sub={`${d.kpis.planned_next_24h} planned to start in the next 24 h`} onClick={() => go('schedule')} />
        <StatCard label="Component units" icon={Package} value={d.kpis.component_units}
                  sub={`${d.kpis.component_lots} lots · ${inv.critical} critical, ${inv.low} low`} onClick={() => go('inventory')} />
      </div>

      {/* progress + needs attention */}
      <div className="grid grid-cols-12 gap-4">
        <Panel title="Assembly progress" subtitle="Share of each stage's work complete — solid to now, projected after" className="col-span-12 xl:col-span-8">
          <div className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {d.stages.map((s) => (
              <div key={s.id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-2">
                  <span className="truncate text-[13px] font-medium text-ink">{s.name.replace(/ – /, ' · ').replace(/ — /, ' · ')}</span>
                  <span className="tabular text-[13px] font-semibold text-ink">{Math.round(s.progress)}%</span>
                </div>
                <Bar value={s.progress} color={STAGE_COLORS[s.id]} />
                <div className="mt-1 text-xs text-ink-3">{s.status} · {s.tasks_done}/{s.tasks_total} tasks{s.tasks_active ? ` · ${s.tasks_active} running` : ''}</div>
              </div>
            ))}
          </div>
          <div className="mt-5 h-64">
            <ResponsiveContainer>
              <LineChart data={pts} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="hour" {...axisProps} interval={3} tickFormatter={day} />
                <YAxis {...axisProps} domain={[0, 100]} ticks={[0, 50, 100]} tickFormatter={(v) => `${v}%`} />
                <Tooltip content={<ChartTooltip unit="%" title={(h) => day(h)} />} cursor={{ stroke: 'rgb(var(--chart-axis))' }} />
                <ReferenceLine x={d.progress.now} stroke="rgb(var(--ink-muted))" strokeDasharray="3 3"
                               label={{ value: 'now', position: 'insideTopLeft', fill: 'rgb(var(--ink-muted))', fontSize: 11 }} />
                {d.stages.map((s) => (
                  <Line key={s.id} type="monotone" dataKey={`s${s.id}`} name={`Stage ${s.id}`} stroke={STAGE_COLORS[s.id]} strokeWidth={2}
                        dot={false} activeDot={{ r: 4, stroke: 'rgb(var(--surface-1))', strokeWidth: 2 }} isAnimationActive={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-ink-3">
            {d.stages.map((s) => (
              <span key={s.id} className="inline-flex items-center gap-1.5">
                <span className="w-4 rounded" style={{ background: STAGE_COLORS[s.id], height: 3 }} />{s.short_name}
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Needs attention" right={<Link onClick={() => go('alerts')}>All alerts</Link>} className="col-span-12 xl:col-span-4" flush>
          {d.alerts.length === 0 ? <EmptyState icon={CheckCircle2} title="Nothing needs attention" body="No open alerts right now." /> : (
            <ul className="divide-y divide-hairline">
              {d.alerts.slice(0, 4).map((a) => {
                const [Icon, color] = SEV[a.severity] || SEV.INFO
                return (
                  <li key={a.id}>
                    <button onClick={() => go('alerts')} className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2">
                      <Icon size={17} className={cx('mt-0.5 shrink-0', color)} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] font-medium leading-snug text-ink">{a.title}</span>
                        <span className="mt-0.5 line-clamp-2 block text-xs text-ink-3">{a.message}</span>
                      </span>
                      <span className="shrink-0 text-[11px] tabular text-ink-muted">{a.time}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>
      </div>

      {/* the two live feeds, side by side */}
      <div className="grid grid-cols-12 gap-4">
        <Panel title="Live activity" subtitle="What the plant is doing right now" className="col-span-12 xl:col-span-8" right={<LiveControls compact />} height={330}>
          <LiveFeed />
        </Panel>
        <AgentBus className="col-span-12 xl:col-span-4" max={14} title="Agent communication" height={330} bodyClass="overflow-y-auto" />
      </div>

      {/* schedule, deliveries, components */}
      <div className="grid grid-cols-12 gap-4">
        <Panel title="Today's schedule" right={<Link onClick={() => go('schedule')}>Full schedule</Link>} className="col-span-12 xl:col-span-6" flush>
          <DataTable dense onRowClick={(r) => openTask(r.id)} rowKey={(r) => r.id}
                     empty={<EmptyState icon={CalendarClock} title="Nothing scheduled" body="No task is running or starting in the next 24 hours." />}
                     columns={[
                       { key: 'id', label: 'Task', className: 'whitespace-nowrap', render: (r) => <span className="mono text-xs text-ink-3">{r.id}</span> },
                       { key: 'name', label: 'Name', render: (r) => <span className="text-ink">{r.name}</span> },
                       { key: 'workstation', label: 'Machine', render: (r) => <span className="mono text-xs">{r.workstation}</span> },
                       { key: 'time', label: 'Starts', className: 'whitespace-nowrap' },
                       { key: 'status', label: '', render: (r) => <Badge tone={r.status === 'In Progress' ? 'cyan' : 'slate'} dot>{r.status}</Badge> },
                     ]} rows={d.todays_schedule} />
        </Panel>

        <Panel title="Upcoming deliveries" right={<Link onClick={() => go('inventory')}>Inventory</Link>} className="col-span-12 xl:col-span-6" flush>
          <DataTable dense onRowClick={(r) => openComponent(r.component_id)} rowKey={(r) => r.id}
                     empty={<EmptyState icon={CheckCircle2} title="All deliveries received" />}
                     columns={[
                       { key: 'component', label: 'Component', render: (r) => <><div className="text-ink">{r.component}</div><div className="mono text-[11px] text-ink-muted">{r.component_id}</div></> },
                       { key: 'eta', label: 'ETA', className: 'whitespace-nowrap', render: (r) => <>{r.eta}{r.delay_hours > 0 && <Badge tone="red" className="ml-1.5">+{r.delay_hours}h</Badge>}</> },
                       { key: 'supplier', label: 'Supplier', className: 'text-ink-3', render: (r) => r.supplier.split(' ').slice(0, 2).join(' ') },
                     ]} rows={d.deliveries.slice(0, 6)} />
        </Panel>

      </div>

      <div className="grid grid-cols-12 gap-4">
        <Panel title="Component status" subtitle={`${totalUnits} units on hand or inbound`} className="col-span-12">
          <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            {GROUPS.map(([k, label]) => {
              const g = d.component_status[k]
              return (
                <li key={k}>
                  <div className="mb-1 flex items-baseline justify-between text-[13px]">
                    <span className="text-ink-2">{label}</span>
                    <span className="tabular text-ink">{g.units}<span className="ml-1 text-xs text-ink-muted">· {g.lots} lots</span></span>
                  </div>
                  <Bar value={(g.units / totalUnits) * 100} color={GROUP_BAD[k] || 'rgb(var(--accent))'} height={5} />
                </li>
              )
            })}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
