import { useState } from 'react'
import { useFetch } from '../ctx'
import { Badge, EmptyState, PageHeader, SearchInput, Spinner, StatusDot, nice, statusTone } from '../ui'

// one tone per lifecycle column, used for a small dot only (never a coloured heading)
const COLS = [
  ['Ordered', ['ORDERED'], 'blue'],
  ['Receiving & inspection', ['RECEIVED', 'INSPECTION_PENDING', 'IN_INSPECTION'], 'amber'],
  ['Cleared · warehouse', ['APPROVED', 'IN_WAREHOUSE'], 'green'],
  ['Assembly bay', ['IN_ASSEMBLY_BAY'], 'cyan'],
  ['Installed', ['INSTALLED'], 'slate'],
  ['Rejected · quarantine', ['REJECTED'], 'red'],
]

export default function Tracking({ openComponent }) {
  const { data, loading } = useFetch('/components', 8000)
  const [q, setQ] = useState('')
  if (loading || !data) return <Spinner />
  const match = (c) => !q || (c.id + c.name).toLowerCase().includes(q.toLowerCase())

  return (
    <div className="space-y-5">
      <PageHeader title="Component tracking" description="Every part moves Ordered → Received → Inspection → Approved → Warehouse → Assembly bay → Installed, or is rejected and replaced. Click a card for its history."
                  actions={<SearchInput className="w-60" placeholder="Find a component…" value={q} onChange={setQ} />} />
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {COLS.map(([title, sts, tone]) => {
          const items = data.filter((c) => sts.includes(c.status))
          const shown = items.filter(match)
          return (
            <section key={title} className="flex min-h-0 flex-col rounded-xl border border-hairline bg-surface-0">
              <header className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
                <StatusDot tone={tone} className="font-medium !text-ink">{title}</StatusDot>
                <span className="rounded-md bg-surface-2 px-1.5 text-xs font-medium tabular text-ink-3">{items.length}</span>
              </header>
              <div className="max-h-[560px] space-y-2 overflow-y-auto px-2 pb-2">
                {shown.length === 0 && <EmptyState title="None" />}
                {shown.map((c) => (
                  <button key={c.id} onClick={() => openComponent(c.id)}
                          className="w-full rounded-lg border border-hairline bg-surface-1 p-2.5 text-left transition-colors hover:bg-surface-2">
                    <div className="flex items-center justify-between">
                      <span className="mono text-[11px] text-ink-muted">{c.id}</span>
                      <span className="text-[11px] text-ink-muted">S{c.stage_id}</span>
                    </div>
                    <div className="mt-0.5 text-[13px] font-medium leading-snug text-ink">{c.name}</div>
                    {c.status !== 'INSTALLED' && (
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
                        {sts.length > 1 && <Badge tone={statusTone(c.status)}>{nice(c.status)}</Badge>}
                        {c.delay_hours > 0 && <Badge tone="red">+{c.delay_hours} h late</Badge>}
                        {c.ready_in_hours > 0 && <span className="tabular">usable in {c.ready_in_hours} h</span>}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </section>
          )
        })}
      </div>
    </div>
  )
}
