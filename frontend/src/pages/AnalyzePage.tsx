import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'

export function AnalyzePage() {
  const [path, setPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!path.trim()) return
    setBusy(true)
    setError(null)
    try {
      const plan = await api.analyzeRepository(path.trim())
      navigate(`/repositories/${plan.repository_id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to analyze repository.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Analyze a repository</h1>
          <p>Give it the path to an already-cloned local git repository.</p>
        </div>
      </div>
      <div className="card">
        <form onSubmit={handleSubmit} className="form-row">
          <input
            type="text"
            placeholder="D:\path\to\cloned-repository"
            value={path}
            onChange={(event) => setPath(event.target.value)}
            disabled={busy}
            autoFocus
          />
          <button type="submit" disabled={busy || !path.trim()}>
            {busy ? 'Analyzing…' : 'Analyze'}
          </button>
        </form>
        <p className="hint">
          Read-only: this scans languages, manifests, tests, and TODOs, and builds a backlog of
          low-risk candidate tasks. Nothing is changed until you approve a task and start a run.
        </p>
        {error && <div className="error-banner" style={{ marginTop: 14 }}>{error}</div>}
      </div>
    </>
  )
}
