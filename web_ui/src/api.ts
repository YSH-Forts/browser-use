// API client for Browser-Use Web UI

const BASE = ''

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`${res.status}: ${err}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  // Sessions
  createSession: () => request<{ session_id: string }>('/api/sessions', { method: 'POST' }),
  executeTask: (sessionId: string, task: string) =>
    request<{ status: string }>(`/api/sessions/${sessionId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task }),
    }),
  getStatus: (sessionId: string) => request<any>(`/api/sessions/${sessionId}/status`),
  stopSession: (sessionId: string) =>
    request<{ status: string }>(`/api/sessions/${sessionId}/stop`, { method: 'POST' }),

  // LLM Config
  getProviders: () => request<{ providers: any[] }>('/api/providers'),
  getLlmConfig: () => request<{ config: any }>('/api/config/llm'),
  updateLlmConfig: (config: any) =>
    request<{ config: any }>('/api/config/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    }),

  // Human Help
  getHumanHelpStatus: (sessionId: string) =>
    request<any>(`/api/sessions/${sessionId}/human-help-status`),
  submitHumanHelp: (sessionId: string, data: any) =>
    request<any>(`/api/sessions/${sessionId}/human-help`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Skills
  getSkills: () => request<{ skills: any[] }>('/api/skills'),
  updateSkill: (id: string, data: { name?: string; description?: string }) =>
    request<any>(`/api/skills/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  deleteSkill: (id: string) =>
    request<any>(`/api/skills/${id}`, { method: 'DELETE' }),
  composeTask: (skillIds: string[]) =>
    request<{ task: string }>('/api/skills/compose', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skill_ids: skillIds }),
    }),

  // Learned Actions
  getLearnedActions: () => request<{ learned_actions: any[] }>('/api/learned-actions'),
  deleteLearnedAction: (key: string) =>
    request<any>(`/api/learned-actions/${encodeURIComponent(key)}`, { method: 'DELETE' }),
}
