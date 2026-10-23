import { useState } from 'react'
import { Search } from 'lucide-react'
import { useFetch } from '../ctx'
import { Badge, Panel, Spinner, nice, statusTone } from '../ui'

const COLS = [
  ['Ordered', ['ORDERED'], '#64748b'], ['Receiving & inspection', ['RECEIVED', 'INSPECTION_PENDING', 'IN_INSPECTION'], '#f59e0b'],
  ['Cleared · warehouse', ['APPROVED', 'IN_WAREHOUSE'], '#22c55e'], ['Assembly bay', ['IN_ASSEMBLY_BAY'], '#22d3ee'], ['Installed', ['INSTALLED'], '#14b8a6'], ['Rejected · quarantine', ['REJECTED'], '#ef4444'],
]

export default function Tracking({ openComponent }) {
  const { data, loading } = useFetch('/components', 8000)
  const [q, setQ] = useState('')
  if (loading || !data) return <Spinner />
  const match = (c) => !q || (c.id + c.name).toLowerCase().includes(q.toLowerCase())
  return (
    <Panel title="Component lifecycle tracking" right={<div className="relative"><Search size={14} className="absolute left-2.5 top-2.5 text-slate-500" /><input className="input !pl-8" placeholder="Find a component…" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
      <p className="mb-3 text-xs text-slate-400">Every part moves through: Ordered → Received → Inspection → Approved → Warehouse → Assembly bay → Installed (or Rejected → replacement). Click a card for its full event history.</p>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">{COLS.map(([title, sts, color]) => {
        const items = data.filter((c) => sts.includes(c.status))
        return (
          <div key={title} className="rounded-xl border border-line bg-space-900/50 p-2.5">
            <div className="mb-2 flex items-center justify-between px-1"><span className="text-[11px] font-semibold uppercase tracking-wider" style={{ color }}>{title}</span><Badge tone="slate">{items.length}</Badge></div>
            <div className="max-h-[520px] space-y-1.5 overflow-y-auto pr-0.5">{items.filter(match).map((c) => (
              <button key={c.id} onClick={() => openComponent(c.id)} className="w-full rounded-lg border border-line bg-space-700/70 p-2 text-left text-xs transition hover:border-accent">
                <div className="flex items-center justify-between"><span className="font-mono text-[11px] text-slate-300">{c.id}</span><span className="text-[10px] text-slate-500">S{c.stage_id}</span></div>
                <div className="mt-0.5 text-slate-100">{c.name}</div>
                {c.status !== 'INSTALLED' && <div className="mt-1 flex flex-wrap gap-1"><Badge tone={statusTone(c.status)}>{nice(c.status)}</Badge>{c.delay_hours > 0 && <Badge tone="red">+{c.delay_hours}h</Badge>}{c.ready_in_hours > 0 && <Badge tone="slate">{c.ready_in_hours}h</Badge>}</div>}
              </button>))}</div>
          </div>)
      })}</div>
    </Panel>
  )
}
