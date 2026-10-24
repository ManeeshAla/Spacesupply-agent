import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import Gantt from '../components/Gantt'
import { useToast } from '../components/Toast'
import { post } from '../api'
import { useApp, useFetch } from '../ctx'
import { Badge, Button, DataTable, PageHeader, Panel, STAGE_COLORS, Select, Spinner, StatusDot, fmtDate, hourToDate, nice, sign, statusTone } from '../ui'

const ALGOS = [['CPSAT', 'OR-Tools CP-SAT'], ['GA', 'Genetic algorithm'], ['PRIORITY', 'Priority rule'], ['FCFS', 'First come, first served']].map(([value, label]) => ({ value, label }))
const FILTERS = [{ value: 'ACTIVE', label: 'Not completed' }, { value: 'ALL', label: 'All tasks' }, { value: 'LATE', label: 'Projected late' }, { value: 'MOVED', label: 'Rescheduled' },
  ...[1, 2, 3, 4].map((s) => ({ value: String(s), label: `Stage ${s}` }))]

export default function Schedule({ openTask }) {
  const { bump, filters } = useApp()
  const toast = useToast()
  const { data, loading } = useFetch('/schedule', 10000)
  const [algo, setAlgo] = useState('CPSAT')
  const [busy, setBusy] = useState(false)
  const [flt, setFlt] = useState('ACTIVE')
  // the assistant can set this filter ("show late tasks", "show stage 2's plan")
  useEffect(() => { if (filters.schedule) setFlt(String(filters.schedule)) }, [filters.schedule])
  if (loading || !data) return <Spinner />

  const m = data.version.metrics
  const replan = async () => {
    setBusy(true)
    try {
      const r = await post('/schedule/replan', { algorithm: algo })
      toast({ tone: r.metrics.tardy_tasks ? 'warn' : 'good', title: `Re-planned with ${algo}`,
        body: `Makespan ${r.metrics.makespan} h · ${r.metrics.tardy_tasks} late · ${r.changes.length} task${r.changes.length === 1 ? '' : 's'} moved (${Math.round(r.metrics.runtime_ms)} ms)` })
      bump()
    } catch (e) { toast({ tone: 'bad', title: 'Re-plan failed', body: e.message }) } finally { setBusy(false) }
  }
  const rows = data.tasks.filter((t) => (flt === 'ALL' ? true : flt === 'ACTIVE' ? t.status !== 'COMPLETED' : flt === 'LATE' ? t.late_hours > 0 : flt === 'MOVED' ? t.shift_hours !== 0 : t.stage_id === +flt))
    .sort((a, b) => (a.start_hour ?? 0) - (b.start_hour ?? 0))
  const dt = (h) => fmtDate(hourToDate(data.start_iso, h))

  return (
    <div className="space-y-5">
      <PageHeader title="Schedule" description="The current optimised plan. Bars are coloured by stage; a red ring means the task is projected to miss its deadline."
                  actions={<>
                    <Select label="Algorithm" value={algo} onChange={setAlgo} options={ALGOS} />
                    <Button variant="primary" icon={RefreshCw} disabled={busy} onClick={replan} className={busy ? '[&_svg]:animate-spin' : ''}>{busy ? 'Re-planning…' : 'Re-plan'}</Button>
                  </>} />

      <Panel title="Assembly Gantt"
             subtitle={<span className="flex flex-wrap items-center gap-x-4 gap-y-1">
               <span>Plan v{data.version.id} · {data.version.algorithm}</span><span className="text-ink-muted">trigger: {data.version.trigger}</span></span>}
             right={<div className="hidden items-center gap-3 text-xs text-ink-3 sm:flex">
               {[1, 2, 3, 4].map((s) => <span key={s} className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: STAGE_COLORS[s] }} />Stage {s}</span>)}</div>}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge tone="blue">Makespan {m.makespan} h</Badge>
          <Badge tone={m.tardy_tasks ? 'red' : 'green'} dot>{m.tardy_tasks} late task{m.tardy_tasks === 1 ? '' : 's'}</Badge>
          <Badge tone="slate">Utilisation {(m.utilization * 100).toFixed(0)}%</Badge>
          <Badge tone={m.conflicts ? 'red' : 'green'} dot>{m.conflicts} conflicts</Badge>
        </div>
        <Gantt data={data} onSelect={openTask} />
        <p className="mt-2.5 text-xs text-ink-muted">Faded = completed · striped = running · click a bar for the full explanation.</p>
      </Panel>

      <Panel flush title={`Tasks · ${rows.length}`} right={<Select label="Filter tasks" value={flt} onChange={setFlt} options={FILTERS} />}>
        <DataTable rows={rows} rowKey={(t) => t.id} onRowClick={(t) => openTask(t.id)} maxHeight={460}
                   columns={[
                     { key: 'id', label: 'Task', render: (t) => <span className="mono text-xs text-ink-3">{t.id}</span> },
                     { key: 'name', label: 'Name', className: 'wrap', render: (t) => <span className="text-ink">{t.name}</span> },
                     { key: 'ws', label: 'Machine', render: (t) => <span className="mono text-xs">{t.workstation}</span> },
                     { key: 'start', label: 'Start', render: (t) => <>{dt(t.start_hour)}{t.shift_hours !== 0 && <Badge tone={t.shift_hours > 0 ? 'amber' : 'green'} className="ml-1.5">{sign(t.shift_hours)}</Badge>}</> },
                     { key: 'end', label: 'End', render: (t) => dt(t.end_hour) },
                     { key: 'prio', label: 'Prio', align: 'right', render: (t) => <span className="tabular">{t.priority}</span> },
                     { key: 'deadline', label: 'Deadline', render: (t) => <>{dt(t.deadline_hour)}{t.late_hours > 0 && <Badge tone="red" className="ml-1.5">+{t.late_hours} h late</Badge>}</> },
                     { key: 'status', label: 'Status', render: (t) => <StatusDot tone={statusTone(t.status)}>{nice(t.status)}</StatusDot> },
                     { key: 'deps', label: 'Depends on', className: 'text-ink-3', render: (t) => <span className="mono text-xs">{t.depends_on.join(', ') || '—'}</span> },
                     { key: 'why', label: 'Why this time', className: 'wrap text-ink-3', render: (t) => <span className="text-xs">{t.reason_text || ''}</span> },
                   ]} />
      </Panel>

      <Panel title="Workstations" subtitle="Live status of the seven machines">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {data.workstations.map((w) => {
            const tone = w.status === 'DOWN' ? 'red' : w.current_task ? 'cyan' : 'green'
            return (
              <div key={w.id} className="rounded-lg border border-hairline bg-surface-0 p-3">
                <div className="flex items-center justify-between"><span className="mono text-[13px] font-semibold text-ink">{w.id}</span>
                  <StatusDot tone={tone} className="!text-xs">{w.status === 'DOWN' ? 'Down' : w.current_task ? 'Busy' : 'Free'}</StatusDot></div>
                <div className="mt-1 text-xs text-ink-3">{w.name}</div>
                <div className="mt-2 text-xs text-ink-2">{w.current_task ? `Running ${w.current_task}` : 'Idle'}{w.free_in_hours > 0 && ` · free in ${w.free_in_hours} h`}</div>
                {w.maintenance_in_hours != null && w.maintenance_in_hours >= 0 && <div className="mt-1 text-[11px] text-t-warning">Maintenance in {Math.round(w.maintenance_in_hours / 24)} d</div>}
              </div>
            )
          })}
        </div>
      </Panel>
    </div>
  )
}
