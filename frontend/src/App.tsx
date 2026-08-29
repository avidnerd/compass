import { useEffect, useRef, useState } from 'react'
import { Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError } from './api/client'
import type { Profile } from './api/types'
import { useWs } from './hooks/useWs'
import { OnboardingProfile } from './pages/OnboardingProfile'
import { OnboardingConnect } from './pages/OnboardingConnect'
import { OnboardingScan } from './pages/OnboardingScan'
import { OnboardingCompanion } from './pages/OnboardingCompanion'
import { Home } from './pages/Home'
import { Quests } from './pages/Quests'
import { QuestNew } from './pages/QuestNew'
import { QuestDetail } from './pages/QuestDetail'
import { CollegeOS } from './pages/CollegeOS'
import { CanvasPage } from './pages/Canvas'
import { FocusSessionPage } from './pages/FocusSessionPage'
import { CharacterCustomize } from './pages/CharacterCustomize'
import { CharacterJournal } from './pages/CharacterJournal'
import { PartyHub } from './pages/PartyHub'
import { PartyDetail } from './pages/PartyDetail'
import { Insights } from './pages/Insights'
import { SettingsConnections } from './pages/SettingsConnections'
import { SettingsPrivacy } from './pages/SettingsPrivacy'
import { SettingsGameplay } from './pages/SettingsGameplay'
import { ReactionToaster } from './pages/ReactionToaster'
import { ResetButton } from './components/ResetButton'
import { PixelIcon } from './components/PixelIcon'

const NAV = [
  { to: '/home', label: 'Home', icon: 'home' },
  { to: '/quests', label: 'Quests', icon: 'quests' },
  { to: '/college', label: 'College', icon: 'college' },
  { to: '/canvas', label: 'Canvas', icon: 'clock' },
  { to: '/party', label: 'Rooms', icon: 'party' },
  { to: '/character/journal', label: 'Journal', icon: 'journal' },
  { to: '/insights', label: 'Insights', icon: 'insights' },
  { to: '/settings/connections', label: 'Settings', icon: 'settings' },
]

/** A pull-down that reaches every destination, including the ones the mobile
 *  dock has no room for. Without it, Settings is unreachable on a phone. */
function GoMenu() {
  const [open, setOpen] = useState(false)
  const menu = useRef<HTMLDivElement>(null)
  const location = useLocation()

  useEffect(() => setOpen(false), [location.pathname])
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => {
      if (menu.current && !menu.current.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  return (
    <div className="menu" ref={menu} data-open={open}>
      <button className="menu-title" aria-expanded={open} aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}>Go</button>
      {open && (
        <ul className="menu-list">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to}>
                <PixelIcon name={item.icon} size={12} /> {item.label}
              </NavLink>
            </li>
          ))}
          <li className="menu-sep" role="separator" />
          <li><NavLink to="/settings/privacy"><PixelIcon name="privacy" size={12} /> Privacy</NavLink></li>
          <li><NavLink to="/settings/gameplay"><PixelIcon name="play" size={12} /> Gameplay</NavLink></li>
        </ul>
      )}
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<Profile>('/me'),
    retry: false,
  })

  const authed = me.isSuccess
  useWs(authed, (event) => {
    window.dispatchEvent(new CustomEvent('compass-event', { detail: event }))
  })

  if (me.isPending) return <main className="center-screen"><p aria-busy="true">Waking Compass…</p></main>


  const unauthenticated = me.isError && (me.error as ApiError)?.status === 401
  const onboarding = location.pathname.startsWith('/onboarding')

  if (unauthenticated && !onboarding) return <Navigate to="/onboarding/profile" replace />

  const profile = me.data?.data

  if (onboarding || unauthenticated) {
    return (
      <main className="onboarding-shell">
        <Routes>
          <Route path="/onboarding/profile" element={<OnboardingProfile />} />
          <Route path="/onboarding/connect" element={<OnboardingConnect />} />
          <Route path="/onboarding/scan" element={<OnboardingScan />} />
          <Route path="/onboarding/companion" element={<OnboardingCompanion />} />
          <Route path="*" element={<Navigate to="/onboarding/profile" replace />} />
        </Routes>
      </main>
    )
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="menubar">
        <span className="brand"><PixelIcon name="compass" size={12} /> Compass</span>
        <GoMenu />
        <span className="menubar-spacer" />
        <span className="menubar-user">
          <span>{profile?.display_name}</span>
          <ResetButton className="nav-reset" />
        </span>
      </div>
      <nav className="desk-icons" aria-label="Primary">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to}
            className={({ isActive }) => `desk-icon ${isActive ? 'active' : ''}`}>
            <PixelIcon name={item.icon} size={36} />
            <span className="desk-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <main id="main" className="main-panel">
        <Routes>
          <Route path="/" element={<Navigate to={profile?.onboarding_step === 'done' ? '/home' : '/onboarding/connect'} replace />} />
          <Route path="/home" element={<Home />} />
          <Route path="/quests" element={<Quests />} />
          <Route path="/quests/new" element={<QuestNew />} />
          <Route path="/quests/:questId" element={<QuestDetail />} />
          <Route path="/college" element={<CollegeOS />} />
          <Route path="/canvas" element={<CanvasPage />} />
          <Route path="/focus/:sessionId" element={<FocusSessionPage />} />
          <Route path="/character/customize" element={<CharacterCustomize />} />
          <Route path="/character/journal" element={<CharacterJournal />} />
          <Route path="/party" element={<PartyHub />} />
          <Route path="/party/:partyId" element={<PartyDetail />} />
          <Route path="/insights/*" element={<Insights />} />
          <Route path="/settings/connections" element={<SettingsConnections />} />
          <Route path="/settings/privacy" element={<SettingsPrivacy />} />
          <Route path="/settings/gameplay" element={<SettingsGameplay />} />
          <Route path="*" element={
            <div className="card">
              <div className="card-header"><h2>File not found</h2></div>
              <p>That page doesn't exist. <NavLink to="/home">Head home</NavLink>.</p>
            </div>} />
        </Routes>
      </main>
      <div className="desk-status" aria-hidden="true">
        <span>{NAV.length} places</span>
        <span>Local · nothing leaves this machine</span>
        <span>Read-only</span>
      </div>
      <nav className="bottom-nav" aria-label="Primary mobile">
        {NAV.slice(0, 5).map((item) => (
          <NavLink key={item.to} to={item.to}
            className={({ isActive }) => `bottom-item ${isActive ? 'active' : ''}`}>
            <PixelIcon name={item.icon} size={24} />
            <span className="bottom-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <ReactionToaster />
    </div>
  )
}
