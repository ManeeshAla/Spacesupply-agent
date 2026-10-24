import { useState } from 'react'
import { useFetch } from '../ctx'
import { Badge, Bar, DataTable, PageHeader, Panel, Select, Spinner, StatCard, StatusDot, cx, nice, statusTone } from '../ui'

const FILTERS = [['ISSUES', 'Needs attention'], ['ALL', 'All active'], ['SUFFICIENT', 'Sufficient'], ['LOW', 'Low'], ['CRITICAL', 'Critical'], ['ON_ORDER', 'On order']]

export default function Inventory({ openComponent }) {
  const inv = useFetch('/inventory', 10000)
  const del = useFetch('/deliveries', 10000)
  const [f, setF] = useState('ISSUES')
  if (inv.loading || !inv.data) return <Spinner />

  const s = inv.data.summary
  const rows = inv.data.rows.filter((r) => (f === 'ALL' ? r.class !== 'DONE' : f === 'ISSUES' ? ['LOW', 'CRITICAL', 'ON_ORDER'].includes(r.class) : r.class === f))
  const tiles = [['SUFFICIENT', 'Sufficient', s.sufficient, 'good'], ['LOW', 'Low stock', s.low, 'warn'], ['CRITICAL', 'Critical', s.critical, 'bad'], ['ON_ORDER', 'On order', s.on_order, undefined]]

  return (
    <div className="space-y-5">
      <PageHeader title="Inventory" description="Whether the parts the plan needs are on hand, on the way, or short. Pick a tile to filter." />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map(([k, label, v, tone]) => (
          <StatCard key={k} label={label} value={v} tone={tone} sub="component lots" onClick={() => setF(k)}
                    className={cx(f === k && 'ring-2 ring-accent')} />
        ))}
      </div>

      <Panel flush title={`${rows.length} lot${rows.length === 1 ? '' : 's'}`}
             right={<Select label="Filter" value={f} onChange={setF} options={FILTERS.map(([value, label]) => ({ value, label }))} />}>
        <DataTable rows={rows} rowKey={(r) => r.id} onRowClick={(r) => openComponent(r.id)} maxHeight={440}
                   columns={[
                     { key: 'id', label: 'ID', render: (r) => <span className="mono text-xs text-ink-3">{r.id}</span> },
                     { key: 'name', label: 'Component', render: (r) => <span className="text-ink">{r.name}</span> },
                     { key: 'stage', label: 'Stage', render: (r) => `S${r.stage_id}` },
                     { key: 'status', label: 'Status', render: (r) => <StatusDot tone={statusTone(r.status)}>{nice(r.status)}</StatusDot> },
                     { key: 'avail', label: 'Available vs required', className: 'w-48', render: (r) => (
                       <div><div className="text-xs tabular text-ink-2">{r.available} / {r.required}</div>
                         <Bar className="mt-1" height={4} value={r.required ? (100 * r.available) / r.required : 100}
                              color={r.shortage ? 'rgb(var(--warning))' : 'rgb(var(--good))'} /></div>) },
                     { key: 'shortage', label: 'Short', align: 'right', render: (r) => <span className="tabular">{r.shortage || '—'}</span> },
                     { key: 'incoming', label: 'Incoming', align: 'right', render: (r) => <span className="tabular">{r.incoming || '—'}</span> },
                     { key: 'eta', label: 'Next ETA', render: (r) => <>{r.next_eta_in != null ? `in ${r.next_eta_in} h` : '—'}{r.delayed && <Badge tone="red" className="ml-1.5">delayed</Badge>}</> },
                     { key: 'supplier', label: 'Supplier', className: 'text-ink-3' },
                   ]} />
      </Panel>

      <Panel flush title="Open deliveries">
        <DataTable rows={del.data || []} rowKey={(d) => d.id} onRowClick={(d) => openComponent(d.component_id)} maxHeight={320}
                   empty={<div className="p-6 text-center text-sm text-ink-3">Every delivery has been received.</div>}
                   columns={[
                     { key: 'id', label: 'Delivery', render: (d) => <span className="mono text-xs text-ink-3">{d.id}</span> },
                     { key: 'component', label: 'Component', render: (d) => <><span className="text-ink">{d.component}</span> <span className="mono text-xs text-ink-muted">{d.component_id}</span>{d.replacement && <Badge tone="amber" className="ml-1.5">replacement</Badge>}</> },
                     { key: 'qty', label: 'Qty', align: 'right', render: (d) => <span className="tabular">{d.quantity}</span> },
                     { key: 'supplier', label: 'Supplier', className: 'text-ink-3' },
                     { key: 'eta', label: 'ETA' },
                     { key: 'in', label: 'In', align: 'right', render: (d) => <span className="tabular">{d.eta_hours > 0 ? `${d.eta_hours} h` : 'arrived'}</span> },
                     { key: 'status', label: 'Status', render: (d) => <StatusDot tone={d.status === 'DELAYED' ? 'red' : d.status === 'ARRIVED' ? 'green' : 'blue'}>{nice(d.status)}{d.delay_hours ? ` +${d.delay_hours} h` : ''}</StatusDot> },
                   ]} />
      </Panel>
    </div>
  )
}
