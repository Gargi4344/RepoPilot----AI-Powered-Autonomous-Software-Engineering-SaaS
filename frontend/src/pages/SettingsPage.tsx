import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Container } from '../components/ui/Container'
import { Card, CardLabel } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { DashboardNav } from '../components/dashboard/DashboardNav'
import { KNOWN_MODELS, PROVIDER_LABEL } from '../lib/aiProviderOptions'
import { cn } from '../lib/cn'
import { ArrowLeft, Bot, CheckCircle2, RefreshCw, XCircle } from 'lucide-react'
import { api, ApiError } from '../api'
import type { AIProviderKind } from '../types'

const PROVIDERS: AIProviderKind[] = ['ollama', 'anthropic', 'gemini']

const inputClass =
  'h-10 w-full rounded-md border border-border bg-surface-2 px-3 text-sm text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent'

export function SettingsPage() {
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [configured, setConfigured] = useState(false)
  const [provider, setProvider] = useState<AIProviderKind>('ollama')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [endpoint, setEndpoint] = useState('http://localhost:11434')
  const [ollamaModels, setOllamaModels] = useState<string[] | null>(null)
  const [refreshingModels, setRefreshingModels] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)

  useEffect(() => {
    api
      .getAiSettings()
      .then((saved) => {
        if (saved) {
          setConfigured(true)
          setProvider(saved.provider)
          setModel(saved.model)
          if (saved.endpoint) setEndpoint(saved.endpoint)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  function changeProvider(next: AIProviderKind) {
    setProvider(next)
    setModel(next === 'ollama' ? '' : KNOWN_MODELS[next][0])
    setApiKey('')
    setTestResult(null)
  }

  async function refreshModels() {
    setRefreshingModels(true)
    setRefreshError(null)
    try {
      const models = await api.listOllamaModels(endpoint)
      setOllamaModels(models)
      if (models.length > 0 && !model) setModel(models[0])
    } catch (err) {
      setRefreshError(err instanceof ApiError ? err.message : 'Failed to reach Ollama.')
    } finally {
      setRefreshingModels(false)
    }
  }

  async function testConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testAiConnection({
        provider,
        model,
        api_key: apiKey || undefined,
        endpoint: provider === 'ollama' ? endpoint : undefined,
      })
      setTestResult({ ok: result.ok, message: result.message })
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof ApiError ? err.message : 'Failed to test the connection.' })
    } finally {
      setTesting(false)
    }
  }

  async function save() {
    setSaving(true)
    setSaveError(null)
    try {
      await api.saveAiSettings({
        provider,
        model,
        api_key: apiKey || undefined,
        endpoint: provider === 'ollama' ? endpoint : undefined,
      })
      setConfigured(true)
      setApiKey('')
      setJustSaved(true)
      setTimeout(() => setJustSaved(false), 3000)
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Failed to save AI settings.')
    } finally {
      setSaving(false)
    }
  }

  const modelOptions = provider === 'ollama' ? ollamaModels : KNOWN_MODELS[provider]
  const canSave = model.trim().length > 0 && (provider === 'ollama' || apiKey.length > 0 || configured)

  return (
    <div className="landing-theme min-h-screen bg-background font-sans text-foreground">
      <DashboardNav />

      <main className="py-10">
        <Container size="narrow">
          <button
            type="button"
            onClick={() => navigate('/repositories')}
            className="flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to repositories
          </button>

          <h1 className="mt-6 text-3xl font-semibold tracking-tight text-foreground">Settings</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">Your account configuration for RepoPilot.</p>

          {loading ? (
            <p className="mt-8 text-sm text-muted-foreground">Loading…</p>
          ) : (
            <Card className="mt-8 p-6">
              <CardLabel>
                <Bot className="h-3.5 w-3.5" />
                AI Model
              </CardLabel>
              <p className="mt-2 text-sm text-muted-foreground">
                RepoPilot uses this one model for every AI operation on your repositories -- analysis, task
                proposals, coding, and review. There is no per-operation override.
              </p>

              <div className="mt-5 grid gap-4">
                <label className="block">
                  <span className="text-xs text-muted-foreground">Provider</span>
                  <select
                    className={cn(inputClass, 'mt-1.5')}
                    value={provider}
                    onChange={(e) => changeProvider(e.target.value as AIProviderKind)}
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p} value={p}>
                        {PROVIDER_LABEL[p]}
                      </option>
                    ))}
                  </select>
                </label>

                {provider === 'ollama' ? (
                  <>
                    <label className="block">
                      <span className="text-xs text-muted-foreground">Endpoint</span>
                      <input
                        type="text"
                        className={cn(inputClass, 'mt-1.5')}
                        value={endpoint}
                        onChange={(e) => setEndpoint(e.target.value)}
                        placeholder="http://localhost:11434"
                      />
                      <span className="mt-1.5 block text-xs text-muted-foreground">
                        If RepoPilot runs in the cloud, this must be an endpoint reachable from the server -- not
                        your own machine's localhost.
                      </span>
                    </label>

                    <div>
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">Model</span>
                        <button
                          type="button"
                          onClick={refreshModels}
                          disabled={refreshingModels}
                          className="flex items-center gap-1 text-xs text-accent transition-colors hover:text-accent/80 disabled:opacity-50"
                        >
                          <RefreshCw className={cn('h-3 w-3', refreshingModels && 'animate-spin')} />
                          {refreshingModels ? 'Refreshing…' : 'Refresh models'}
                        </button>
                      </div>
                      {modelOptions && modelOptions.length > 0 ? (
                        <select className={cn(inputClass, 'mt-1.5')} value={model} onChange={(e) => setModel(e.target.value)}>
                          {!modelOptions.includes(model) && model && <option value={model}>{model}</option>}
                          {modelOptions.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          className={cn(inputClass, 'mt-1.5')}
                          value={model}
                          onChange={(e) => setModel(e.target.value)}
                          placeholder="e.g. qwen2.5-coder:7b"
                        />
                      )}
                      {refreshError && <p className="mt-1.5 text-xs text-destructive">{refreshError}</p>}
                    </div>
                  </>
                ) : (
                  <>
                    <label className="block">
                      <span className="text-xs text-muted-foreground">API Key</span>
                      <input
                        type="password"
                        className={cn(inputClass, 'mt-1.5')}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder={configured ? '••••••••••••••••••••• (unchanged)' : 'sk-...'}
                        autoComplete="off"
                      />
                    </label>

                    <label className="block">
                      <span className="text-xs text-muted-foreground">Model</span>
                      <select className={cn(inputClass, 'mt-1.5')} value={model} onChange={(e) => setModel(e.target.value)}>
                        {KNOWN_MODELS[provider].map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                  </>
                )}
              </div>

              {testResult && (
                <div
                  className={cn(
                    'mt-5 flex items-center gap-2 rounded-md border px-3.5 py-2.5 text-sm',
                    testResult.ok
                      ? 'border-accent/40 bg-accent/10 text-accent'
                      : 'border-destructive/40 bg-destructive/10 text-destructive',
                  )}
                >
                  {testResult.ok ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
                  {testResult.ok ? 'Connected successfully.' : testResult.message}
                </div>
              )}
              {saveError && (
                <div className="mt-5 rounded-md border border-destructive/40 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive">
                  {saveError}
                </div>
              )}

              <div className="mt-6 flex items-center gap-3">
                <Button variant="secondary" onClick={testConnection} disabled={testing || !model.trim()}>
                  {testing ? 'Testing…' : 'Test Connection'}
                </Button>
                <Button variant="accent" onClick={save} disabled={saving || !canSave}>
                  {saving ? 'Saving…' : 'Save Changes'}
                </Button>
                {justSaved && <span className="text-sm text-accent">Saved.</span>}
              </div>
            </Card>
          )}
        </Container>
      </main>
    </div>
  )
}
