// Shared TypeScript types for the Browser-Use Web UI

export interface LlmProvider {
  id: string
  name: string
  description: string
  class: string
  default_model: string
  fields: string[]
}

export interface LlmConfig {
  provider: string
  model?: string
  api_key?: string
  base_url?: string
  temperature?: number
  max_tokens?: number
  top_p?: number
  timeout?: number
  extra: Record<string, any>
}

export interface Skill {
  id: string
  name: string
  description: string
  action_type: string
  params: Record<string, any>
  context: { url: string; title: string }
  created_at: string
  session_id: string
  step_index: number
}

export interface LearnedAction {
  url_pattern: string
  button_text: string
  target_url: string
  description: string
  question: string
  element_index?: number
  learned_at: string
}

export interface StepData {
  step: number
  timestamp: string
  thinking?: string
  evaluation?: string
  memory?: string
  next_goal?: string
  actions: Record<string, any>[]
  action_labels: string[]
  url?: string
  title?: string
  llm_trace?: LlmTrace | null
}

export interface LlmTrace {
  timestamp: string
  model: string | null
  stop_reason: string | null
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  } | null
  input: LlmMessage[]
  output: {
    thinking: string
    evaluation: string
    memory: string
    next_goal: string
    actions: Record<string, any>[]
  }
}

export interface LlmMessage {
  role: string
  text: string
  images?: string[]
  tool_calls?: {
    id: string
    name: string
    args: string
  }[]
}

export interface HumanHelpPayload {
  session_id: string
  question: string
  url: string
  timestamp: string
}

export type TaskStatus = 'idle' | 'running' | 'done' | 'stopping' | 'error'
