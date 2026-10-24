import { useEffect, useState } from 'react'
import { useApp, useFetch } from '../ctx'
import { Badge, DataTable, PageHeader, Panel, SearchInput, Select, Spinner, StatusDot, nice, statusTone } from '../ui'

const GROUPS = ['all', 'available', 'in_inspection', 'in_assembly', 'installed', 'on_order', 'rejected']
const CRIT = { CRITICAL: 'red', HIGH: 'amber' }

export default function Components({ openComponent }) {
  const { filters } = useApp()
  const { data, loading } = useFetch('/components', 10000)
  const [q, setQ] = useState('')
  const [g, setG] = useState('all')
  const [stage, setStage] = useState(0)
  // the assistant can set these filters ("show me rejected parts in stage 2")
  useEffect(() => { if (filters.query != null) setQ(filters.query) }, [filters.query])
  useEffect(() => { if (filters.stage != null) setStage(Number(filters.stage) || 0) }, [filters.stage])
  if (loading || !data) return <Spinner />

  const rows = data.filter((c) => (g === 'all' || c.group === g) && (!stage || c.stage_id === stage) &&
    (!q || (c.id + c.name + c.location + c.supplier).toLowerCase().includes(q.toLowerCase())))

  return (
    <div className="space-y-5">
      <PageHeader title="Components" description={`${data.length} component lots across the four stages. Click a row for its full lifecycle history.`} />
      <Panel flush title={`${rows.length} of ${data.length} lots`}
             right={<>
               <SearchInput className="w-56" placeholder="Search id, name, location…" value={q} onChange={setQ} />
               <Select label="Lifecycle group" value={g} onChange={setG} options={GROUPS.map((x) => ({ value: x, label: x === 'all' ? 'All statuses' : nice(x) }))} />
               <Select label="Stage" value={String(stage)} onChange={(v) => setStage(+v)}
                       options={[{ value: '0', label: 'All stages' }, ...[1, 2, 3, 4].map((s) => ({ value: String(s), label: `Stage ${s}` }))]} />
             </>}>
        <DataTable rows={rows} rowKey={(c) => c.id} onRowClick={(c) => openComponent(c.id)} maxHeight="calc(100dvh - 15rem)"
                   columns={[
                     { key: 'id', label: 'ID', render: (c) => <span className="mono text-xs text-ink-3">{c.id}</span> },
                     { key: 'name', label: 'Name', render: (c) => <span className="text-ink">{c.name}</span> },
                     { key: 'stage', label: 'Stage', render: (c) => `S${c.stage_id}` },
                     { key: 'status', label: 'Status', render: (c) => <span className="inline-flex items-center gap-1.5"><StatusDot tone={statusTone(c.status)}>{nice(c.status)}</StatusDot>{c.delay_hours > 0 && <Badge tone="red">+{c.delay_hours}h</Badge>}</span> },
                     { key: 'location', label: 'Location', className: 'text-ink-3' },
                     { key: 'qty', label: 'On hand / req.', align: 'right', render: (c) => <span className="tabular">{c.quantity} / {c.required}</span> },
                     { key: 'insp', label: 'Inspection', className: 'text-ink-3', render: (c) => nice(c.inspection_status) },
                     { key: 'crit', label: 'Criticality', render: (c) => (CRIT[c.criticality] ? <Badge tone={CRIT[c.criticality]}>{nice(c.criticality)}</Badge> : <span className="text-ink-muted">{nice(c.criticality)}</span>) },
                     { key: 'ready', label: 'Usable in', align: 'right', render: (c) => <span className="tabular">{c.ready_in_hours ? `${c.ready_in_hours} h` : '—'}</span> },
                   ]} />
      </Panel>
    </div>
  )
}
