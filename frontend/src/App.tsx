import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { RequireAuth } from './components/RequireAuth'
import { LandingPage } from './pages/LandingPage'
import { RepositoriesPage } from './pages/RepositoriesPage'
import { AnalyzePage } from './pages/AnalyzePage'
import { BacklogPage } from './pages/BacklogPage'
import { AutopilotPage } from './pages/AutopilotPage'
import { RunDetailPage } from './pages/RunDetailPage'
import { ActivityPage } from './pages/ActivityPage'
import { SettingsPage } from './pages/SettingsPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route
        path="repositories"
        element={
          <RequireAuth>
            <RepositoriesPage />
          </RequireAuth>
        }
      />
      <Route
        path="repositories/:id"
        element={
          <RequireAuth>
            <BacklogPage />
          </RequireAuth>
        }
      />
      <Route
        path="repositories/:id/autopilot"
        element={
          <RequireAuth>
            <AutopilotPage />
          </RequireAuth>
        }
      />
      <Route
        path="runs/:id"
        element={
          <RequireAuth>
            <RunDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="settings"
        element={
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        }
      />
      <Route
        path="activity"
        element={
          <RequireAuth>
            <ActivityPage />
          </RequireAuth>
        }
      />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="analyze" element={<AnalyzePage />} />
      </Route>
    </Routes>
  )
}

export default App
