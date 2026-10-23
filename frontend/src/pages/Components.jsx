import { useState } from 'react'
import { Search } from 'lucide-react'
import { useFetch } from '../ctx'
import { Badge, Panel, Spinner, nice, statusTone } from '../ui'

const GROUPS = ['all', 'available', 'in_inspection', 'in_assembly', 'installed', 'on_order', 'rejected']

export default function Components({ openComponent }) {
  const { data, loading } = useFetch('/components', 10000)
  const [q, setQ] = useState('')
  const [g, setG] = useState('all')
  const [stage, setStage] = useState(0)
  if (loading || !data) return <Spinner />
  const rows = data.filter((c) => (g === 'all' || c.group === g) && (!stage || c.stage_id === stage) &&
    (!q || (c.id + c.name + c.location + c.supplier).toLowerCase().includes(q.toLowerCase())))
  return (
    <Panel title={`Components (${rows.length} of ${data.length} lots)`}
           right={<div className="flex flex-wrap items-center gap-2">
             <div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" /><input className="input !pl-8" placeholder="Search id, name, location…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
             <select className="input" value={g} onChange={(e) => setG(e.target.value)}>{GROUPS.map((x) => <option key={x} value={x}>{nice(x)}</option>)}</select>
             <select className="input" value={stage} onChange={(e) => setStage(+e.target.value)}><option value={0}>All stages</option>{[1, 2, 3, 4].map((s) => <option key={s} value={s}>Stage {s}</option>)}</select></div>}>
      <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight: 'calc(100vh - 300px)' }}>
        <table className="w-full"><thead className="sticky top-0 bg-space-700"><tr>{['ID', 'Name', 'Category', 'Stage', 'Status', 'Location', 'On hand / Req.', 'Inspection', 'Criticality', 'Usable in'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{rows.map((c) => (
            <tr key={c.id} onClick={() => openComponent(c.id)} className="cursor-pointer border-t border-line/50 hover:bg-space-700/60">
              <td className="td font-mono text-xs">{c.id}</td><td className="td">{c.name}</td><td className="td text-slate-400">{nice(c.category)}</td><td className="td">S{c.stage_id}</td>
              <td className="td"><Badge tone={statusTone(c.status)}>{nice(c.status)}</Badge>{c.delay_hours > 0 && <Badge tone="red" className="ml-1">delayed {c.delay_hours}h</Badge>}</td>
              <td className="td text-slate-300">{c.location}</td><td className="td">{c.quantity} / {c.required}</td><td className="td text-slate-400">{nice(c.inspection_status)}</td>
              <td className="td"><Badge tone={c.criticality === 'CRITICAL' ? 'red' : c.criticality === 'HIGH' ? 'amber' : 'slate'}>{c.criticality}</Badge></td>
              <td className="td">{c.ready_in_hours ? `${c.ready_in_hours}h` : '—'}</td></tr>))}</tbody></table>
      </div>
    </Panel>
  )
}
