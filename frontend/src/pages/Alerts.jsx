import { useState } from 'react'
import { AlertTriangle, Check, Info, OctagonAlert } from 'lucide-react'
import { post } from '../api'
import { useApp, useFetch } from '../ctx'
import { Badge, Panel, Spinner, sevTone } from '../ui'

export default function Alerts({ openTask, openComponent }) {
  const { bump } = useApp()
  const { data, loading } = useFetch('/alerts', 8000)
  const [f, setF] = useState('OPEN')
  const [sev, setSev] = useState('ALL')
  if (loading || !data) return <Spinner />
  const rows = data.filter((a) => (f === 'ALL' || a.status === f) && (sev === 'ALL' || a.severity === sev))
  const Icon = ({ s }) => (s === 'CRITICAL' ? <OctagonAlert className="text-bad" size={20} /> : s === 'WARNING' ? <AlertTriangle className="text-warn" size={20} /> : <Info className="text-accent-soft" size={20} />)
  return (
    <Panel title={`Alerts (${rows.length})`} right={<div className="flex gap-2">
      <select className="input" value={f} onChange={(e) => setF(e.target.value)}>{['OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'ALL'].map((x) => <option key={x}>{x}</option>)}</select>
      <select className="input" value={sev} onChange={(e) => setSev(e.target.value)}>{['ALL', 'CRITICAL', 'WARNING', 'INFO'].map((x) => <option key={x}>{x}</option>)}</select></div>}>
      <ul className="space-y-2">{rows.length === 0 && <li className="p-4 text-sm text-slate-400">Nothing here.</li>}{rows.map((a) => (
        <li key={a.id} className="flex gap-3 rounded-xl border border-line bg-space-900/60 p-3"><Icon s={a.severity} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium text-white">{a.title}</span><Badge tone={sevTone(a.severity)}>{a.severity}</Badge><Badge tone="slate">{a.category.replace(/_/g, ' ').toLowerCase()}</Badge>
              {a.status !== 'OPEN' && <Badge tone={a.status === 'RESOLVED' ? 'green' : 'blue'}>{a.status.toLowerCase()}</Badge>}</div>
            <p className="mt-1 text-sm text-slate-300">{a.message}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">{a.time}
              {a.task_id && <button className="text-accent-soft hover:underline" onClick={() => openTask(a.task_id)}>{a.task_id}</button>}
              {a.component_id && <button className="text-accent-soft hover:underline" onClick={() => openComponent(a.component_id)}>{a.component_id}</button>}</div>
          </div>
          {a.status === 'OPEN' && <button className="btn h-fit" onClick={async () => { await post(`/alerts/${a.id}/ack`); bump() }}><Check size={14} />Acknowledge</button>}
        </li>))}</ul>
    </Panel>
  )
}
