export function formatEventTime(ts: string): string {
  return new Date(ts).toLocaleTimeString([], { hour12: false })
}

// The coding agent logs tool calls as "tool name(args) -> result" -- split that into a
// command line and its output so it can be styled like a terminal command, distinct from
// a plain status message.
export function splitToolMessage(message: string): { command: string | null; output: string } {
  const isTool = message.startsWith('tool ')
  const arrowIndex = message.indexOf(' -> ')
  if (!isTool || arrowIndex < 0) return { command: null, output: message }
  return { command: message.slice(0, arrowIndex), output: message.slice(arrowIndex + 4) }
}

export function isEventLevelAttention(level: string): boolean {
  return level === 'error' || level === 'warning'
}
