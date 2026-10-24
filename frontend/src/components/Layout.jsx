import { useEffect, useMemo, useState } from 'react'
import {
  Activity, BarChart3, Bell, Boxes, CalendarClock, Command, LayoutDashboard, Menu, Moon, Network, Package, PanelLeftClose,
  PanelLeftOpen, Plus, Rocket, Route, Search, Sparkles, Sun, X, Zap,
} from 'lucide-react'
import { useApp, useFetch } from '../ctx'
import { useTheme } from '../theme'
import { cx, IconButton } from '../ui'
import CommandPalette from './CommandPalette'
import { LiveControls, LiveDot } from './Live'

export const NAV = [
  { label: 'Operate', items: [
    ['dashboard', 'Dashboard', LayoutDashboard], ['schedule', 'Schedule', CalendarClock],
    ['tracking', 'Tracking', Route], ['alerts', 'Alerts', Bell]] },
  { label: 'Supply', items: [['components', 'Components', Boxes], ['inventory', 'Inventory', Package]] },
  { label: 'Intelligence', items: [['chat', 'Assistant', Sparkles], ['agents', 'Agents', Network], ['reports', 'Reports', BarChart3]] },
]
const TITLES = Object.fromEntries(NAV.flatMap((g) => g.items.map(([id, label]) => [id, label])))
const STATUS_TONE = { OPERATIONAL: 'bg-good', ATTENTION: 'bg-warning', DEGRADED: 'bg-critical' }

function Sidebar({ page, go, collapsed, setCollapsed, mobile, onNavigate, alerts, status }) {
  const slim = collapsed && !mobile
  return (
    <nav aria-label="Main" className={cx('flex h-full flex-col border-r border-hairline bg-surface-0', slim ? 'w-[68px]' : 'w-60')}>
      <div className={cx('flex h-14 shrink-0 items-center gap-2.5 border-b border-hairline px-3.5', slim && 'justify-center px-0')}>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-solid text-accent-ink"><Rocket size={16} /></div>
        {!slim && <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold tracking-tight text-ink">SpaceSupply</div>
          <div className="truncate text-[11px] text-ink-muted">Assembly control</div></div>}
        {mobile && <IconButton label="Close menu" onClick={onNavigate}><X size={16} /></IconButton>}
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto px-2.5 py-4">
        {NAV.map((g) => (
          <div key={g.label}>
            {!slim && <div className="eyebrow mb-1.5 px-2.5">{g.label}</div>}
            <ul className="space-y-0.5">
              {g.items.map(([id, label, Icon]) => {
                const on = page === id
                return (
                  <li key={id}>
                    <button onClick={() => { go(id); onNavigate?.() }} aria-current={on ? 'page' : undefined} title={slim ? label : undefined}
                            className={cx('group relative flex w-full items-center gap-3 rounded-lg py-2 text-[13px] font-medium transition-colors',
                              slim ? 'justify-center px-0' : 'px-2.5',
                              on ? 'bg-surface-2 text-ink' : 'text-ink-3 hover:bg-surface-2/70 hover:text-ink')}>
                      {on && <span className="absolute left-0 top-1.5 h-5 w-[3px] rounded-r bg-accent" />}
                      <Icon size={17} className={on ? 'text-t-accent' : 'text-ink-muted group-hover:text-ink-2'} />
                      {!slim && <span className="flex-1 text-left">{label}</span>}
                      {id === 'alerts' && alerts > 0 && (
                        <span className={cx('rounded-full bg-critical/15 px-1.5 text-[11px] font-semibold tabular text-t-critical', slim && 'absolute right-1.5 top-0.5 !px-1 text-[10px]')}>{alerts}</span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="shrink-0 space-y-2 border-t border-hairline p-3">
        {!slim && (
          <div className="rounded-lg bg-surface-1 p-2.5 ring-1 ring-hairline">
            <div className="flex items-center gap-2 text-xs font-medium text-ink-2">
              <span className={cx('h-2 w-2 rounded-full', STATUS_TONE[status] || 'bg-ink-muted')} />System {status ? status.toLowerCase() : '…'}
            </div>
            <div className="mt-1 text-[11px] leading-snug text-ink-muted">Synthetic data. Not affiliated with ISRO or any space agency.</div>
          </div>
        )}
        {!mobile && (
          <button onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                  className={cx('flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink', slim && 'justify-center px-0')}>
            {collapsed ? <PanelLeftOpen size={16} /> : <><PanelLeftClose size={16} />Collapse</>}
          </button>
        )}
      </div>
    </nav>
  )
}

export default function Layout({ page, go, openSim, children }) {
  const { data: d } = useFetch('/dashboard', 8000)
  const { live, chat } = useApp()
  const [theme, toggleTheme] = useTheme()
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem('spacesupply-nav') === '1' } catch { return false } })
  const [menu, setMenu] = useState(false)
  const [palette, setPalette] = useState(false)

  useEffect(() => { try { localStorage.setItem('spacesupply-nav', collapsed ? '1' : '0') } catch { /* ignore */ } }, [collapsed])
  useEffect(() => {
    const onKey = (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p) } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const items = useMemo(() => [
    ...NAV.flatMap((g) => g.items.map(([id, label, icon]) => ({ id: `go-${id}`, group: 'Go to', label, icon, run: () => go(id) }))),
    { id: 'play', group: 'Actions', label: live.running ? 'Pause live mode' : 'Play live mode', icon: Activity, run: () => live.setRunning(!live.running) },
    { id: 'scenario', group: 'Actions', label: 'Trigger a scenario…', icon: Zap, run: openSim },
    { id: 'theme', group: 'Actions', label: theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme', icon: theme === 'dark' ? Sun : Moon, run: toggleTheme },
    { id: 'newchat', group: 'Actions', label: 'New assistant chat', icon: Plus, run: () => { chat.newChat(); go('chat') } },
  ], [go, live, openSim, theme, toggleTheme, chat])

  const ask = (q) => { go('chat'); chat.send(q) }
  const status = d?.system_status
  const alerts = d?.kpis?.pending_alerts || 0
  const now = d ? new Date(d.now_iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '…'

  return (
    <div className="flex h-full bg-plane text-ink">
      <div className="hidden md:block"><Sidebar page={page} go={go} collapsed={collapsed} setCollapsed={setCollapsed} alerts={alerts} status={status} /></div>
      {menu && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/50 animate-fade-in" onClick={() => setMenu(false)} />
          <div className="absolute inset-y-0 left-0 animate-slide-in"><Sidebar page={page} go={go} mobile onNavigate={() => setMenu(false)} alerts={alerts} status={status} /></div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-hairline bg-plane/90 px-4 py-2.5 backdrop-blur md:px-6">
          <IconButton label="Open menu" className="md:hidden" onClick={() => setMenu(true)}><Menu size={18} /></IconButton>
          <div className="min-w-0 flex-1 md:flex-none">
            <div className="truncate text-sm font-semibold tracking-tight text-ink">{TITLES[page] || 'SpaceSupply'}</div>
            <div className="flex items-center gap-1.5 text-xs text-ink-3" data-testid="plant-clock" data-now={d?.now_iso || ''}>
              <LiveDot />Plant time <span className="tabular text-ink-2">{now}</span>
            </div>
          </div>

          <div className="hidden flex-1 md:block" />
          <button onClick={() => setPalette(true)} aria-label="Open command palette"
                  className="hidden h-9 items-center gap-2 rounded-lg border border-hairline bg-surface-0 px-3 text-[13px] text-ink-muted transition-colors hover:text-ink lg:flex lg:w-56">
            <Search size={14} />Search or ask…<span className="ml-auto flex items-center gap-0.5 text-[11px]"><Command size={11} />K</span>
          </button>
          <IconButton label="Search or ask (Ctrl+K)" className="lg:hidden" onClick={() => setPalette(true)}><Search size={17} /></IconButton>
          <LiveControls />
          <button onClick={openSim} className="btn" title="Trigger a specific disruption by hand"><Zap size={14} /><span className="hidden sm:inline">Scenario</span></button>
          <IconButton label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'} onClick={toggleTheme}>
            {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
          </IconButton>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto"><div className="mx-auto w-full max-w-[1500px] p-4 md:p-6">{children}</div></main>
      </div>

      <CommandPalette open={palette} onClose={() => setPalette(false)} items={items} onAsk={ask} />
    </div>
  )
}
