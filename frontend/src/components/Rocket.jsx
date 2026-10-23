import { STAGE_COLORS } from '../ui'

/** Original, generic multi-stage launch-vehicle schematic; fill level = stage assembly progress. */
export default function Rocket({ stages = [] }) {
  const byId = Object.fromEntries(stages.map((s) => [s.id, s]))
  const p = (id) => (byId[id]?.progress ?? 0) / 100
  const col = (id) => (byId[id]?.status === 'Completed' ? '#22c55e' : byId[id]?.status === 'Pending' ? '#64748b' : STAGE_COLORS[id])
  const base = '#16224d'
  const stroke = '#3b4f8f'

  // geometry (viewBox 960 x 230)
  const S1 = { x: 70, w: 270 }      // strap-on boosters
  const S2 = { x: 230, w: 330 }     // core
  const S3 = { x: 560, w: 150 }     // upper motor
  const S4 = { x: 710, w: 100 }     // avionics bay
  const labels = [
    { id: 1, x: S1.x + S1.w / 2 - 35 }, { id: 2, x: S2.x + S2.w / 2 + 40 },
    { id: 3, x: S3.x + S3.w / 2 }, { id: 4, x: S4.x + S4.w / 2 + 70 },
  ]
  const fill = (id, x, w, y, h, rx = 6) => (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={rx} fill={base} stroke={stroke} />
      <clipPath id={`c${id}${x}${y}`}><rect x={x} y={y} width={w} height={h} rx={rx} /></clipPath>
      <rect x={x} y={y} width={w * p(id)} height={h} fill={col(id)} opacity="0.85" clipPath={`url(#c${id}${x}${y})`} />
      <rect x={x} y={y} width={w} height={h * 0.28} fill="white" opacity="0.07" rx={rx} />
    </g>
  )
  return (
    <svg viewBox="0 0 960 230" className="h-full w-full" role="img" aria-label="Launch vehicle assembly progress by stage">
      <defs>
        <linearGradient id="flame" x1="1" x2="0"><stop offset="0" stopColor="#fde68a" /><stop offset="1" stopColor="#f97316" stopOpacity="0" /></linearGradient>
      </defs>
      {/* stage labels */}
      {labels.map(({ id, x }) => (
        <g key={id} textAnchor="middle" fontFamily="Inter, sans-serif">
          <text x={x} y="22" fontSize="14" fontWeight="600" fill={col(id)}>Stage {id}</text>
          <text x={x} y="40" fontSize="11" fill="#94a3b8">{byId[id]?.status ?? ''}</text>
          <text x={x} y="62" fontSize="17" fontWeight="700" fill={col(id)}>{byId[id]?.progress ?? 0}%</text>
        </g>
      ))}
      {/* dividers */}
      {[S2.x, S3.x, S4.x].map((x, i) => <line key={i} x1={x} x2={x} y1="14" y2="215" stroke="#24356d" strokeDasharray="3 5" opacity=".7" />)}
      {/* engine flame hint */}
      <path d="M 70 120 L 20 112 L 20 128 Z" fill="url(#flame)" opacity=".5" />
      {/* Stage 1 boosters (two strap-ons) */}
      {fill(1, S1.x, S1.w, 78, 34)}
      {fill(1, S1.x, S1.w, 128, 34)}
      <path d={`M ${S1.x + S1.w} 78 L ${S1.x + S1.w + 38} 95 L ${S1.x + S1.w} 112 Z`} fill={col(1)} opacity={0.4 + 0.5 * p(1)} stroke={stroke} />
      <path d={`M ${S1.x + S1.w} 128 L ${S1.x + S1.w + 38} 145 L ${S1.x + S1.w} 162 Z`} fill={col(1)} opacity={0.4 + 0.5 * p(1)} stroke={stroke} />
      {[78, 128].map((y) => <rect key={y} x={S1.x - 14} y={y + 8} width="14" height="18" rx="3" fill="#0b1330" stroke={stroke} />)}
      {/* Stage 2 core */}
      {fill(2, S2.x + 60, S2.w - 60, 88, 54)}
      <rect x={S2.x + 40} y="100" width="20" height="30" rx="3" fill="#0b1330" stroke={stroke} />
      {/* Stage 3 */}
      {fill(3, S3.x, S3.w, 94, 42)}
      {/* Stage 4 bay + fairing */}
      {fill(4, S4.x, S4.w, 98, 34)}
      <path d={`M ${S4.x + S4.w} 98 C ${S4.x + S4.w + 70} 98, ${S4.x + S4.w + 110} 108, ${S4.x + S4.w + 130} 115 C ${S4.x + S4.w + 110} 122, ${S4.x + S4.w + 70} 132, ${S4.x + S4.w} 132 Z`}
            fill={p(4) > 0 ? col(4) : base} opacity={p(4) > 0 ? 0.8 : 1} stroke={stroke} />
      <text x={S2.x + S2.w / 2 + 20} y="120" textAnchor="middle" fontSize="13" letterSpacing="6" fill="#cbd5e1" opacity=".55" fontFamily="Inter, sans-serif">SPACESUPPLY</text>
      <text x="480" y="222" textAnchor="middle" fontSize="10" fill="#64748b" fontFamily="Inter, sans-serif">Schematic of a simulated multi-stage vehicle · fill = assembly progress</text>
    </svg>
  )
}
