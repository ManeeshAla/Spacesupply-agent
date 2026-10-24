import { useEffect, useState } from 'react'
import { AlertTriangle, Check, CheckCheck, CheckCircle2, Info, OctagonAlert } from 'lucide-react'
import { post } from '../api'
import { useApp, useFetch } from '../ctx'
import { useToast } from '../components/Toast'
import { Button, EmptyState, PageHeader, Panel, Segmented, Select, Spinner, cx, nice } from '../ui'

const SEV = [
  ['CRITICAL', 'Critical', OctagonAlert, 'text-t-critical'],
  ['WARNING', 'Warning', AlertTriangle, 'text-t-warning'],
  ['INFO', 'Info', Info, 'text-t-accent'],
]
const STATUS_OPTIONS = [['OPEN', 'Open'], ['ACKNOWLEDGED', 'Acknowledged'], ['RESOLVED', 'Resolved'], ['ALL', 'All']].map(([value, label]) => ({ value, label }))

export default function Alerts({ openTask, openComponent }) {
  const { bump, filters } = useApp()
  const toast = useToast()
  const { data, loading } = useFetch('/alerts', 8000)
  const [f, setF] = useState('OPEN')
  const [sev, setSev] = useState('ALL')
  const [stage, setStage] = useState(0)
  // the assistant can set these filters ("show critical alerts for stage 3")
  useEffect(() => { if (filters.alertStatus) setF(filters.alertStatus) }, [filters.alertStatus])
  useEffect(() => { if (filters.alertSeverity) setSev(filters.alertSeverity) }, [filters.alertSeverity])
  useEffect(() => { if (filters.alertStage != null) setStage(Number(filters.alertStage) || 0) }, [filters.alertStage])
  if (loading || !data) return <Spinner />

  const rows = data.filter((a) => (f === 'ALL' || a.status === f) && (sev === 'ALL' || a.severity === sev) && (!stage || a.stage_id === stage))
  const open = rows.filter((a) => a.status === 'OPEN')
  const ack = async (list) => {
    await Promise.all(list.map((a) => post(`/alerts/${a.id}/ack`)))
    bump()
    toast({ tone: 'good', title: list.length === 1 ? 'Alert acknowledged' : `${list.length} alerts acknowledged`, duration: 3000 })
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Alerts" description="Raised automatically by the Monitoring Agent: late deliveries, failed inspections, machine downtime and projected lateness."
                  actions={open.length > 1 && <Button icon={CheckCheck} onClick={() => ack(open)}>Acknowledge all {open.length}</Button>} />

      <div className="flex flex-wrap items-center gap-2">
        <Segmented value={f} onChange={setF} options={STATUS_OPTIONS} />
        <Select label="Severity" value={sev} onChange={setSev} options={[{ value: 'ALL', label: 'All severities' }, ...SEV.map(([v, l]) => ({ value: v, label: l }))]} />
        <Select label="Stage" value={String(stage)} onChange={(v) => setStage(+v)} options={[{ value: '0', label: 'All stages' }, ...[1, 2, 3, 4].map((s) => ({ value: String(s), label: `Stage ${s}` }))]} />
      </div>

      {rows.length === 0 && <Panel><EmptyState icon={CheckCircle2} title="Nothing here" body="No alerts match these filters." /></Panel>}

      {SEV.map(([key, label, Icon, color]) => {
        const group = rows.filter((a) => a.severity === key)
        if (!group.length) return null
        return (
          <Panel key={key} flush title={<span className="flex items-center gap-2"><Icon size={15} className={color} />{label}<span className="text-ink-muted">· {group.length}</span></span>}>
            <ul className="divide-y divide-hairline">
              {group.map((a) => (
                <li key={a.id} className="flex items-start gap-4 px-4 py-3.5">
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] font-medium leading-snug text-ink">{a.title}</div>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-3">{a.message}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-muted">
                      <span className="tabular">{a.time}</span>
                      <span>{nice(a.category)}</span>
                      {a.task_id && <button className="mono text-t-accent hover:underline" onClick={() => openTask(a.task_id)}>{a.task_id}</button>}
                      {a.component_id && <button className="mono text-t-accent hover:underline" onClick={() => openComponent(a.component_id)}>{a.component_id}</button>}
                      {a.status !== 'OPEN' && <span className={cx('font-medium', a.status === 'RESOLVED' ? 'text-t-good' : 'text-ink-3')}>{nice(a.status)}</span>}
                    </div>
                  </div>
                  {a.status === 'OPEN' && <Button size="sm" icon={Check} onClick={() => ack([a])}>Acknowledge</Button>}
                </li>
              ))}
            </ul>
          </Panel>
        )
      })}
    </div>
  )
}
