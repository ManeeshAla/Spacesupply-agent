import { useState } from 'react'
import { useFetch } from '../ctx'
import { Badge, Bar, Panel, Spinner, nice, statusTone } from '../ui'

export default function Inventory({ openComponent }) {
  const inv = useFetch('/inventory', 10000)
  const del = useFetch('/deliveries', 10000)
  const [f, setF] = useState('ISSUES')
  if (inv.loading || !inv.data) return <Spinner />
  const s = inv.data.summary
  const rows = inv.data.rows.filter((r) => (f === 'ALL' ? r.class !== 'DONE' : f === 'ISSUES' ? ['LOW', 'CRITICAL', 'ON_ORDER'].includes(r.class) : r.class === f))
  const tiles = [['SUFFICIENT', 'Sufficient', s.sufficient, '#22c55e'], ['LOW', 'Low stock', s.low, '#f59e0b'], ['CRITICAL', 'Critical', s.critical, '#ef4444'], ['ON_ORDER', 'On order', s.on_order, '#3b82f6']]
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{tiles.map(([k, label, v, c]) => (
        <button key={k} onClick={() => setF(k)} className={`panel p-4 text-left transition hover:border-accent ${f === k ? '!border-accent' : ''}`}>
          <div className="text-[11px] font-semibold uppercase tracking-wider" style={{ color: c }}>{label}</div><div className="mt-1 text-3xl font-bold text-white">{v}</div><div className="text-xs text-slate-500">component lots</div></button>))}</div>
      <Panel title={`Inventory · ${rows.length} lot(s)`} right={<select className="input" value={f} onChange={(e) => setF(e.target.value)}>
        {[['ISSUES', 'Needs attention'], ['ALL', 'All active'], ['SUFFICIENT', 'Sufficient'], ['LOW', 'Low'], ['CRITICAL', 'Critical'], ['ON_ORDER', 'On order']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}>
        <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight: 420 }}>
          <table className="w-full"><thead className="sticky top-0 bg-space-700"><tr>{['ID', 'Component', 'Stage', 'Status', 'Available vs required', 'Shortage', 'Incoming', 'Next ETA', 'Supplier', 'Class'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.id} onClick={() => openComponent(r.id)} className="cursor-pointer border-t border-line/50 hover:bg-space-700/60">
                <td className="td font-mono text-xs">{r.id}</td><td className="td">{r.name}</td><td className="td">S{r.stage_id}</td><td className="td"><Badge tone={statusTone(r.status)}>{nice(r.status)}</Badge></td>
                <td className="td w-44"><div className="text-xs text-slate-300">{r.available} / {r.required}</div><Bar value={r.required ? (100 * r.available) / r.required : 100} color={r.shortage ? '#f59e0b' : '#22c55e'} className="mt-1" /></td>
                <td className="td">{r.shortage || '—'}</td><td className="td">{r.incoming || '—'}</td><td className="td">{r.next_eta_in != null ? `in ${r.next_eta_in}h` : '—'}{r.delayed && <Badge tone="red" className="ml-1">delayed</Badge>}</td>
                <td className="td text-slate-400">{r.supplier}</td><td className="td"><Badge tone={statusTone(r.class)}>{nice(r.class)}</Badge></td></tr>))}</tbody></table>
        </div>
      </Panel>
      <Panel title="Open deliveries">
        <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight: 300 }}>
          <table className="w-full"><thead className="sticky top-0 bg-space-700"><tr>{['Delivery', 'Component', 'Qty', 'Supplier', 'ETA', 'In', 'Status'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
            <tbody>{(del.data || []).map((d) => (
              <tr key={d.id} onClick={() => openComponent(d.component_id)} className="cursor-pointer border-t border-line/50 hover:bg-space-700/60">
                <td className="td font-mono text-xs">{d.id}</td><td className="td">{d.component_id} · {d.component}{d.replacement && <Badge tone="amber" className="ml-1">replacement</Badge>}</td><td className="td">{d.quantity}</td><td className="td text-slate-400">{d.supplier}</td>
                <td className="td">{d.eta}</td><td className="td">{d.eta_hours > 0 ? `${d.eta_hours}h` : 'arrived'}</td><td className="td"><Badge tone={d.status === 'DELAYED' ? 'red' : d.status === 'ARRIVED' ? 'green' : 'blue'}>{nice(d.status)}{d.delay_hours ? ` +${d.delay_hours}h` : ''}</Badge></td></tr>))}</tbody></table>
        </div>
      </Panel>
    </div>
  )
}
