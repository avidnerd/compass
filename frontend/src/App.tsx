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
import { FocusSessionPage } from './pages/FocusSessionPage'
import { CharacterCustomize } from './pages/CharacterCustomize'
import { CharacterJournal } from './pages/CharacterJournal'
import { BattleHub } from './pages/BattleHub'
import { BattleRoom } from './pages/BattleRoom'
import { PartyHub } from './pages/PartyHub'
import { PartyDetail } from './pages/PartyDetail'
import { BossScene } from './pages/BossScene'
import { Insights } from './pages/Insights'
import { Leaderboards } from './pages/Leaderboards'
import { SettingsConnections } from './pages/SettingsConnections'
import { SettingsPrivacy } from './pages/SettingsPrivacy'
import { SettingsGameplay } from './pages/SettingsGameplay'
import { ReactionToaster } from './pages/ReactionToaster'
import { ResetButton } from './components/ResetButton'

const NAV = [
  { to: '/home', label: 'Home', icon: '🏡' },
  { to: '/quests', label: 'Quests', icon: '🗺️' },
  { to: '/college', label: 'College', icon: '🎓' },
  { to: '/battle', label: 'Battle', icon: '⚔️' },
  { to: '/party', label: 'Party', icon: '🎪' },
  { to: '/character/journal', label: 'Journal', icon: '📖' },
  { to: '/leaderboards', label: 'Ranks', icon: '🏆' },
  { to: '/insights', label: 'Insights', icon: '📊' },
  { to: '/settings/connections', label: 'Settings', icon: '⚙️' },
]

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
      <nav className="side-nav" aria-label="Primary">
        <div className="brand">🧭 Compass</div>
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span aria-hidden="true">{item.icon}</span> {item.label}
          </NavLink>
        ))}
        <div className="nav-footer">
          <div>{profile?.display_name}</div>
          <ResetButton className="nav-reset" />
        </div>
      </nav>
      <main id="main" className="main-panel">
        <Routes>
          <Route path="/" element={<Navigate to={profile?.onboarding_step === 'done' ? '/home' : '/onboarding/connect'} replace />} />
          <Route path="/home" element={<Home />} />
          <Route path="/quests" element={<Quests />} />
          <Route path="/quests/new" element={<QuestNew />} />
          <Route path="/quests/:questId" element={<QuestDetail />} />
          <Route path="/college" element={<CollegeOS />} />
          <Route path="/focus/:sessionId" element={<FocusSessionPage />} />
          <Route path="/character/customize" element={<CharacterCustomize />} />
          <Route path="/character/journal" element={<CharacterJournal />} />
          <Route path="/leaderboards" element={<Leaderboards />} />
          <Route path="/battle" element={<BattleHub />} />
          <Route path="/battle/:battleId" element={<BattleRoom />} />
          <Route path="/party" element={<PartyHub />} />
          <Route path="/party/:partyId" element={<PartyDetail />} />
          <Route path="/party/:partyId/boss/:encounterId" element={<BossScene />} />
          <Route path="/insights/*" element={<Insights />} />
          <Route path="/settings/connections" element={<SettingsConnections />} />
          <Route path="/settings/privacy" element={<SettingsPrivacy />} />
          <Route path="/settings/gameplay" element={<SettingsGameplay />} />
          <Route path="*" element={
            <div className="card"><h2>Lost in the meadow (404)</h2>
              <p>That page doesn't exist. <NavLink to="/home">Head home</NavLink>.</p></div>} />
        </Routes>
      </main>
      <nav className="bottom-nav" aria-label="Primary mobile">
        {NAV.slice(0, 5).map((item) => (
          <NavLink key={item.to} to={item.to}
            className={({ isActive }) => `bottom-item ${isActive ? 'active' : ''}`}>
            <span aria-hidden="true">{item.icon}</span>
            <span className="bottom-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <ReactionToaster />
    </div>
  )
}
