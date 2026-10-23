import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useFetch } from '../ctx'
import { Badge, Panel, Spinner } from '../ui'

const COLORS = { FCFS: '#64748b', PRIORITY: '#3b82f6', GA: '#a78bfa', CPSAT: '#22c55e' }
const tip = { contentStyle: { background: '#101a3d', border: '1px solid #1c2b5a', borderRadius: 8 } }
const pct = (v) => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)

function Suite({ name, s }) {
  const algs = Object.entries(s.algorithms)
  const data = algs.map(([a, v]) => ({ name: a, objective: v.objective, tardy: v.tardy_tasks, makespan: v.makespan }))
  return (
    <Panel title={`${name} — ${s.scenarios} perturbed scenarios · ${s.jobs_per_scenario} tasks · ${s.machines} workstations`} className="col-span-12 xl:col-span-6">
      <div className="h-48">
        <ResponsiveContainer><BarChart data={data}><CartesianGrid stroke="#1c2b5a" strokeDasharray="3 3" /><XAxis dataKey="name" stroke="#94a3b8" fontSize={11} /><YAxis stroke="#94a3b8" fontSize={11} /><Tooltip {...tip} />
          <Bar isAnimationActive={false} dataKey="objective" name="Mean objective (lower = better)" fill="#3b82f6" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>
      </div>
      <table className="mt-2 w-full"><thead><tr>{['Algorithm', 'Objective', 'Makespan h', 'Tardy tasks', 'Conflicts', 'Runtime ms', 'Best/tied'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody>{algs.map(([a, v]) => (<tr key={a} className="border-t border-line/50"><td className="td"><span className="mr-2 inline-block h-2 w-2 rounded-sm" style={{ background: COLORS[a] }} />{a}</td>
          <td className="td">{v.objective}</td><td className="td">{v.makespan}</td><td className="td">{v.tardy_tasks}</td><td className="td">{v.conflicts}</td><td className="td">{v.runtime_ms}</td><td className="td">{v.wins_or_ties_best}/{s.scenarios}</td></tr>))}</tbody></table>
    </Panel>
  )
}

const CAT_LABEL = {
  read: 'Read questions', follow_up: 'Follow-ups (memory)', ui: 'Dashboard control',
  action: 'Actions (confirmation)', tricky: 'Tricky / no data', off_topic: 'Off-topic',
}

/** Evaluation of the Gemini supervisor: produced by `python scripts/eval_chat.py`. */
function ChatEval({ ev, gemini }) {
  if (!ev) {
    return (
      <Panel title="Chat assistant evaluation" className="col-span-12">
        <p className="text-sm text-slate-400">
          Not run yet. With a Gemini key in <code className="text-slate-300">backend/.env</code>, run
          <code className="ml-1 text-slate-300">python scripts/eval_chat.py</code> from <code className="text-slate-300">backend/</code> to
          score 46 questions (reads, follow-ups, dashboard control, actions, tricky wording, off-topic) against the
          real API. The numbers land here.
        </p>
        {gemini && (
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge tone={gemini.configured ? 'green' : 'amber'}>
              {gemini.configured ? 'Gemini key detected' : 'no Gemini key – chat uses the offline Micro LM'}
            </Badge>
            <Badge tone="slate">{gemini.model}</Badge>
          </div>
        )}
      </Panel>
    )
  }
  const o = ev.overall
  const cats = Object.entries(ev.by_category || {}).map(([k, v]) => ({ name: CAT_LABEL[k] || k, accuracy: v.accuracy, n: v.n }))
  const cards = [
    ['Overall accuracy', `${o.accuracy}%`], ['Correct tool chosen', `${o.tool_choice_accuracy}%`],
    ['Answer content', `${o.answer_accuracy}%`], ['Grounded answers', `${o.grounded}%`],
    ['Confirmation respected', o.confirmation_respected == null ? '–' : `${o.confirmation_respected}%`],
    ['Dashboard commands', o.ui_command_accuracy == null ? '–' : `${o.ui_command_accuracy}%`],
    ['Fell back to Micro LM', `${o.fallback_rate}%`],
    ['Latency median / p90', `${o.latency_ms_median ?? '–'} / ${o.latency_ms_p90 ?? '–'} ms`],
  ]
  return (
    <>
      <Panel title={`Chat assistant evaluation · ${ev.questions} questions on ${ev.model}`} className="col-span-12 xl:col-span-7"
             right={<Badge tone="slate">{ev.generated_at}</Badge>}>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {cards.map(([k, v]) => (
            <div key={k} className="rounded-lg bg-space-900/60 p-3">
              <dt className="text-[11px] uppercase tracking-wider text-slate-400">{k}</dt>
              <dd className="mt-1 font-semibold text-white">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-xs text-slate-400">
          A question counts as passed only if the right tool was called, the answer contained what it should
          (and nothing it should not), the grounding guard passed, an action stopped for confirmation, and the
          model did not fall back. Run in {ev.duration_s}s, paced for the free tier.
        </p>
      </Panel>
      <Panel title="Accuracy by question type" className="col-span-12 xl:col-span-5">
        <div className="h-64">
          <ResponsiveContainer>
            <BarChart data={cats} layout="vertical" margin={{ left: 60 }}>
              <CartesianGrid stroke="#1c2b5a" strokeDasharray="3 3" />
              <XAxis type="number" domain={[0, 100]} stroke="#94a3b8" fontSize={11} />
              <YAxis type="category" dataKey="name" interval={0} stroke="#94a3b8" fontSize={10} width={130} />
              <Tooltip {...tip} formatter={(v, _n, p) => [`${v}%  (n=${p.payload.n})`, 'accuracy']} />
              <Bar isAnimationActive={false} dataKey="accuracy" fill="#22d3ee" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
      {ev.failures?.length > 0 && (
        <Panel title={`Evaluation failures (${ev.failures.length})`} className="col-span-12" bodyClass="max-h-64 overflow-y-auto">
          <ul className="space-y-2 text-xs">
            {ev.failures.map((f) => (
              <li key={f.id} className="rounded bg-space-900/60 p-2">
                <div className="text-slate-100">“{f.question}”</div>
                <div className="mt-1 text-red-300">{f.notes.join(' · ')}</div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  )
}

export default function Reports() {
  const model = useFetch('/model')
  const cmp = useFetch('/schedule/compare')
  const ver = useFetch('/schedule/versions')
  if (model.loading || cmp.loading) return <Spinner label="Loading evaluation…" />
  const m = model.data || {}
  const t = m.test || {}
  const intents = Object.entries(t.per_intent || {}).map(([k, v]) => ({ name: k.replace(/_/g, ' '), f1: v.f1, precision: v.precision, recall: v.recall }))
  const cm = t.confusion_matrix
  const labels = m.intents || []
  const bench = cmp.data?.benchmark
  return (
    <div className="grid grid-cols-12 gap-4">
      <div className="col-span-12 rounded-xl border border-warn/30 bg-warn/10 px-4 py-2 text-xs text-amber-200">
        All numbers on this page are measured on <b>synthetic data</b> generated for this prototype. The test split uses sentence templates never seen in training; the held-out result is the honest one.
      </div>
      <div className="col-span-12 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-300">Chat assistant · Gemini supervisor with tool calling</div>
      <ChatEval ev={m.chat_eval} gemini={m.gemini_layer} />
      <div className="col-span-12 mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-300">Micro Language Model · local PyTorch model</div>
      <Panel title="Micro Language Model" className="col-span-12 xl:col-span-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          {[['Trainable parameters', (m.parameters || 0).toLocaleString()], ['Framework', m.framework], ['Vocabulary', m.vocab_size], ['Inference', `${m.inference_ms} ms/query`],
            ['Intent accuracy (held-out)', pct(t.intent_accuracy)], ['Macro F1', pct(t.f1_macro)], ['Entity F1', pct(t.entity_f1)], ['Perplexity (LM head)', t.lm_perplexity],
            ['Hand-written challenge', pct(m.challenge?.intent_accuracy)], ['Training time', `${m.training_seconds}s`]].map(([k, v]) => (
            <div key={k} className="rounded-lg bg-space-900/60 p-3"><dt className="text-[11px] uppercase tracking-wider text-slate-400">{k}</dt><dd className="mt-1 font-semibold text-white">{v}</dd></div>))}
        </dl>
        <p className="mt-3 text-xs text-slate-400">{m.architecture}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Badge tone={m.qwen_layer?.enabled ? 'green' : 'slate'}>Qwen layer: {m.qwen_layer?.enabled ? 'on' : 'off (Ollama not detected)'}</Badge>
          <Badge tone="slate">{m.qwen_layer?.model}</Badge>
          <Badge tone={m.gemini_layer?.configured ? 'green' : 'slate'}>Gemini supervisor: {m.gemini_layer?.configured ? 'on' : 'off (no API key)'}</Badge>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          The Micro LM still runs first on every question (intent + entity hint) and powers chat autocomplete.
          It is also the offline fallback when Gemini is unreachable or out of free quota.
        </p>
      </Panel>
      <Panel title="Training curve" className="col-span-12 xl:col-span-8">
        <div className="h-64"><ResponsiveContainer><LineChart data={m.history || []}><CartesianGrid stroke="#1c2b5a" strokeDasharray="3 3" /><XAxis dataKey="epoch" stroke="#94a3b8" fontSize={11} /><YAxis stroke="#94a3b8" fontSize={11} /><Tooltip {...tip} /><Legend />
          <Line isAnimationActive={false} dataKey="train_loss" stroke="#f59e0b" dot={false} name="Train loss" /><Line isAnimationActive={false} dataKey="val_intent_acc" stroke="#22c55e" dot={false} name="Val intent acc" /><Line isAnimationActive={false} dataKey="val_entity_f1" stroke="#3b82f6" dot={false} name="Val entity F1" /></LineChart></ResponsiveContainer></div>
      </Panel>
      <Panel title="Per-intent F1 (held-out templates)" className="col-span-12 xl:col-span-7">
        <div className="h-72"><ResponsiveContainer><BarChart data={intents} layout="vertical" margin={{ left: 100 }}><CartesianGrid stroke="#1c2b5a" strokeDasharray="3 3" /><XAxis type="number" domain={[0, 1]} stroke="#94a3b8" fontSize={11} /><YAxis type="category" dataKey="name" interval={0} stroke="#94a3b8" fontSize={10} width={110} /><Tooltip {...tip} />
          <Bar isAnimationActive={false} dataKey="f1" fill="#a78bfa" radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></div>
      </Panel>
      <Panel title="Challenge-set misses (hand-written queries)" className="col-span-12 xl:col-span-5">
        <ul className="space-y-2 text-xs">{(m.challenge?.failures || []).map((f, i) => (<li key={i} className="rounded bg-space-900/60 p-2"><div className="text-slate-100">“{f.text}”</div><div className="mt-1 text-slate-400">expected {f.gold} · got <span className="text-red-300">{f.pred}</span></div></li>))}
          {!(m.challenge?.failures || []).length && <li className="text-slate-400">No misses.</li>}</ul>
      </Panel>
      {cm && (
        <Panel title="Confusion matrix (rows = true, cols = predicted)" className="col-span-12">
          <div className="overflow-x-auto"><table className="text-[10px]"><thead><tr><th />{labels.map((l, i) => <th key={i} className="px-1 py-1 text-slate-400" title={l}>{i}</th>)}</tr></thead>
            <tbody>{cm.map((row, i) => { const tot = row.reduce((a, b) => a + b, 0) || 1; return (<tr key={i}><td className="pr-2 text-right text-slate-400">{i} {labels[i]}</td>
              {row.map((v, j) => <td key={j} className="h-6 w-8 text-center" style={{ background: `rgba(59,130,246,${(v / tot) * (i === j ? 0.9 : 1.2)})`, color: v ? '#fff' : '#334' }}>{v || ''}</td>)}</tr>) })}</tbody></table></div>
        </Panel>
      )}
      <div className="col-span-12 mt-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-300">Scheduler comparison · objective = 10 × priority-weighted tardiness + makespan</div>
      {bench && Object.entries(bench.suites).map(([k, s]) => <Suite key={k} name={k === 'single_vehicle' ? 'Single vehicle' : 'Three-vehicle campaign'} s={s} />)}
      <Panel title="Live schedule — all algorithms on the current plant state" className="col-span-12 xl:col-span-6">
        <table className="w-full"><thead><tr>{['Algorithm', 'Objective', 'Makespan', 'Tardy', 'Runtime ms'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody>{(cmp.data?.live || []).map((r) => (<tr key={r.algorithm} className="border-t border-line/50"><td className="td">{r.algorithm}{r.optimal ? ' ✓ optimal' : ''}</td><td className="td">{r.objective}</td><td className="td">{r.makespan}</td><td className="td">{r.tardy_tasks}</td><td className="td">{r.runtime_ms}</td></tr>))}</tbody></table>
      </Panel>
      <Panel title="Schedule version history" className="col-span-12 xl:col-span-6" bodyClass="max-h-64 overflow-y-auto">
        <ul className="space-y-2 text-xs">{(ver.data || []).map((v) => (<li key={v.id} className="flex items-center gap-2 rounded bg-space-900/60 p-2"><Badge tone={v.current ? 'green' : 'slate'}>v{v.id}</Badge><Badge tone="blue">{v.algorithm}</Badge><span className="flex-1 text-slate-300">{v.trigger}</span><span className="text-slate-500">{v.time}</span></li>))}</ul>
      </Panel>
    </div>
  )
}
