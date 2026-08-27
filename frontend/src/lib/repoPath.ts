export function describeRepoPath(path: string): { name: string; source: string } {
  const normalized = path.replace(/\\/g, '/')
  const match = normalized.match(/\/github\/([^/]+)__([^/]+)\/?$/)
  if (match) return { name: `${match[1]}/${match[2]}`, source: 'GitHub repository' }
  return { name: path, source: 'Local repository' }
}
