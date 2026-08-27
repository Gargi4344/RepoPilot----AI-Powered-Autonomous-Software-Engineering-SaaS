import type { AIProviderKind } from '../types'

export const PROVIDER_LABEL: Record<AIProviderKind, string> = {
  ollama: 'Ollama',
  anthropic: 'Anthropic (Claude)',
  gemini: 'Gemini',
}

// Mirrors the curated lists in app/ai/providers/{anthropic,gemini}_provider.py -- these two
// providers only accept models RepoPilot has confirmed support tool-calling. Ollama has no
// fixed list: any locally pulled model is valid, fetched live via "Refresh models".
export const KNOWN_MODELS: Record<Exclude<AIProviderKind, 'ollama'>, string[]> = {
  anthropic: ['claude-opus-5', 'claude-sonnet-5', 'claude-haiku-4-5-20251001', 'claude-opus-4-8', 'claude-opus-4-7'],
  gemini: ['gemini-3.5-flash', 'gemini-3-pro', 'gemini-2.5-flash', 'gemini-2.5-pro'],
}
