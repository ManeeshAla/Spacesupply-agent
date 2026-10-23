import { useFetch } from '../ctx'
import { Badge, Drawer, Spinner, nice, statusTone, sign } from '../ui'

export function ComponentDrawer({ id, onClose, onTask }) {
  const { data, loading } = useFetch(id ? `/components/${id}` : '/health')
  if (!id) return null
  return (
    <Drawer open onClose={onClose} title={data ? `${data.id} · ${data.name}` : id}>
      {loading || !data?.history ? <Spinner /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Badge tone={statusTone(data.status)}>{nice(data.status)}</Badge>
            <Badge tone="slate">{data.category}</Badge>
            <Badge tone={data.criticality === 'CRITICAL' ? 'red' : data.criticality === 'HIGH' ? 'amber' : 'slate'}>{data.criticality}</Badge>
            {data.delay_hours > 0 && <Badge tone="red">delayed {data.delay_hours}h</Badge>}
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            {[['Location', data.location], ['Stage', `Stage ${data.stage_id}`], ['On hand', data.quantity], ['Required', data.required],
              ['Inspection', nice(data.inspection_status)], ['Supplier', data.supplier],
              ['Usable in', data.ready_in_hours ? `${data.ready_in_hours}h` : 'now']].map(([k, v]) => (
              <div key={k} className="rounded-lg border border-line bg-space-900/60 p-2.5"><dt className="text-[11px] uppercase tracking-wider text-slate-400">{k}</dt><dd className="mt-0.5 text-slate-100">{v}</dd></div>
            ))}
          </dl>
          {data.delivery && <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-sm">Delivery <b>{data.delivery.id}</b> · {data.delivery.quantity} unit(s) · ETA in {data.delivery.eta_in}h · {nice(data.delivery.status)}{data.delivery.delay_hours ? ` · delayed ${data.delivery.delay_hours}h` : ''}</div>}
          <div>
            <h4 className="panel-title mb-2">Used by tasks</h4>
            <div className="flex flex-wrap gap-2">{data.used_by.map((t) => (
              <button key={t.task_id} onClick={() => onTask(t.task_id)} className="btn !py-1 text-xs">{t.task_id} · {t.name} <Badge tone={statusTone(t.status)}>{nice(t.status)}</Badge></button>
            ))}</div>
          </div>
          <div>
            <h4 className="panel-title mb-3">Event history</h4>
            <ol className="relative space-y-3 border-l border-line pl-5">
              {data.history.slice().reverse().map((e, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full bg-accent ring-4 ring-space-800" />
                  <div className="text-sm font-medium text-slate-100">{nice(e.event)}</div>
                  <div className="text-xs text-slate-400">{e.time}{e.location ? ` · ${e.location}` : ''}</div>
                  {e.note && <div className="text-xs text-slate-300">{e.note}</div>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Drawer>
  )
}

export function TaskDrawer({ id, onClose, onComponent }) {
  const { data, loading } = useFetch(id ? `/tasks/${id}` : '/health')
  if (!id) return null
  const r = data?.readiness, ex = data?.explanation
  return (
    <Drawer open onClose={onClose} title={r ? `${r.task_id} · ${r.name}` : id}>
      {loading || !r ? <Spinner /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            <Badge tone={statusTone(r.status)}>{nice(r.status)}</Badge>
            {r.status === 'PENDING' && <Badge tone={r.can_start_now ? 'green' : 'red'}>{r.can_start_now ? 'Ready to start now' : `Blocked (${r.blockers.length})`}</Badge>}
            {ex?.late_hours > 0 && <Badge tone="red">{ex.late_hours}h past deadline</Badge>}
            {ex?.shift_hours !== 0 && ex?.shift_hours != null && <Badge tone={ex.shift_hours > 0 ? 'amber' : 'green'}>{sign(ex.shift_hours)} vs original plan</Badge>}
          </div>
          {r.summary && <p className="text-sm text-slate-300">{r.summary}</p>}
          {r.status === 'PENDING' && r.planned_workstation && (
            <p className="text-sm text-slate-300">Planned on <b>{r.planned_workstation}</b>, starting in <b>{Math.max(0, r.planned_in_hours)}h</b>.</p>
          )}
          {r.blockers.length > 0 && (
            <div>
              <h4 className="panel-title mb-2">What is blocking it right now</h4>
              <ul className="space-y-1.5 text-sm">{r.blockers.map((b, i) => <li key={i} className="rounded-lg border border-line bg-space-900/60 p-2.5"><Badge tone={b.type === 'COMPONENT' ? 'amber' : b.type === 'WORKSTATION' ? 'blue' : 'slate'}>{b.type}</Badge> <span className="ml-1">{b.text}</span></li>)}</ul>
            </div>
          )}
          {ex?.chain?.length > 0 && (
            <div>
              <h4 className="panel-title mb-2">Why it is scheduled when it is</h4>
              <ol className="list-decimal space-y-1.5 pl-5 text-sm text-slate-200">{ex.chain.map((c, i) => <li key={i}>{c}</li>)}</ol>
            </div>
          )}
          <div>
            <h4 className="panel-title mb-2">Required components</h4>
            <div className="overflow-hidden rounded-lg border border-line">
              <table className="w-full"><thead className="bg-space-700"><tr><th className="th">Component</th><th className="th">Need</th><th className="th">Status</th></tr></thead>
                <tbody>{(r.components.length ? r.components : data.requirements.map((q) => ({ id: q.component_id, name: q.name, needed: q.quantity, status: 'INSTALLED' }))).map((c) => (
                  <tr key={c.id} className="cursor-pointer border-t border-line/60 hover:bg-space-700/60" onClick={() => onComponent(c.id)}>
                    <td className="td">{c.id} · {c.name}</td><td className="td">{c.needed}</td>
                    <td className="td"><Badge tone={statusTone(c.status)}>{nice(c.status)}</Badge>{c.eta_hours > 0 && <span className="ml-1 text-xs text-slate-400">~{c.eta_hours}h</span>}</td>
                  </tr>))}</tbody></table>
            </div>
          </div>
        </div>
      )}
    </Drawer>
  )
}
