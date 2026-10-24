/* One chart look for the whole app (dataviz method): recessive hairline grid, muted axis ink,
   no default legends or tooltip chrome, stage colours from the validated ordinal ramp.
   Colours are CSS variables, so charts follow the light/dark theme with no re-render logic. */

export const INK = {
  axis: 'rgb(var(--chart-axis))',
  grid: 'rgb(var(--chart-grid))',
  label: 'rgb(var(--ink-muted))',
  text: 'rgb(var(--ink-2))',
  accent: 'rgb(var(--accent))',
  surface: 'rgb(var(--surface-1))',
}

export const axisProps = {
  stroke: INK.axis,
  tick: { fill: INK.label, fontSize: 12 },
  tickLine: false,
  axisLine: { stroke: INK.axis },
}

export const gridProps = { stroke: INK.grid, strokeDasharray: '0', vertical: false }

/** Tooltip card in the app's own panel style. `rows(payload)` may be given to customise lines. */
export function ChartTooltip({ active, payload, label, unit = '', title }) {
  if (!active || !payload?.length) return null
  return (
    <div className="panel min-w-[9rem] px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{title ? title(label, payload) : label}</div>
      {payload.filter((p) => p.value != null).map((p) => (
        <div key={p.dataKey || p.name} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-ink-3">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color || p.stroke || p.fill }} />{p.name}
          </span>
          <span className="tabular font-medium text-ink">{typeof p.value === 'number' ? Math.round(p.value * 10) / 10 : p.value}{unit}</span>
        </div>
      ))}
    </div>
  )
}
