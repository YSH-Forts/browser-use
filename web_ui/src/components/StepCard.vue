<template>
  <div
    class="step-card"
    :class="{ hidden: !visible }"
    @click="$emit('toggle')"
  >
    <div class="step-header">
      <span class="step-num">Step {{ step.step }}</span>
      <span v-if="evalText" class="step-eval-badge" :class="evalClass">{{ truncate(evalText, 60) }}</span>
      <span class="step-actions-summary">{{ actionChips || 'processing...' }}</span>
      <span class="step-url">{{ step.url ? truncate(step.url, 30) : '' }}</span>
      <span v-if="step.llm_trace" class="llm-trace-badge" title="LLM trace available">&#9670; LLM</span>
    </div>
    <div class="step-body" :class="{ open: isOpen }">
      <!-- LLM Trace Panel (LangSmith-like) -->
      <template v-if="step.llm_trace">
        <div class="llm-panel" @click.stop>
          <div class="llm-panel-header" @click="llmOpen = !llmOpen">
            <span class="llm-panel-title">
              &#9670; LLM Trace
              <span class="llm-model" v-if="step.llm_trace.model">{{ step.llm_trace.model }}</span>
            </span>
            <div class="llm-stats">
              <span v-if="step.llm_trace.usage" class="llm-token" :title="`${step.llm_trace.usage.total_tokens} total tokens`">
                {{ step.llm_trace.usage.prompt_tokens }} in / {{ step.llm_trace.usage.completion_tokens }} out
              </span>
              <span v-if="step.llm_trace.stop_reason" class="llm-stop">{{ step.llm_trace.stop_reason }}</span>
            </div>
            <span class="llm-toggle">{{ llmOpen ? '&#9660;' : '&#9654;' }}</span>
          </div>

          <div class="llm-panel-body" v-if="llmOpen">
            <!-- Input Messages -->
            <div class="llm-section">
              <div class="llm-section-label">Input ({{ step.llm_trace.input.length }} messages)</div>
              <div
                v-for="(msg, i) in step.llm_trace.input"
                :key="i"
                class="llm-msg"
                :class="`role-${msg.role}`"
              >
                <div class="llm-msg-header">
                  <span class="llm-role">{{ msg.role }}</span>
                  <span v-if="msg.images?.length" class="llm-images">&#128247; {{ msg.images.length }} image(s)</span>
                  <span v-if="msg.tool_calls?.length" class="llm-tools">{{ msg.tool_calls.length }} tool call(s)</span>
                </div>
                <div class="llm-msg-text" v-if="msg.text">{{ msg.text }}</div>
                <div class="llm-tool-calls" v-if="msg.tool_calls?.length">
                  <div v-for="tc in msg.tool_calls" :key="tc.id" class="llm-tool-call">
                    <span class="llm-tool-name">{{ tc.name }}</span>
                    <pre class="llm-tool-args">{{ formatArgs(tc.args) }}</pre>
                  </div>
                </div>
              </div>
            </div>

            <!-- Output -->
            <div class="llm-section">
              <div class="llm-section-label">Output</div>

              <template v-if="step.llm_trace.output.thinking">
                <div class="llm-output-label">Thinking</div>
                <div class="llm-output thinking">{{ step.llm_trace.output.thinking }}</div>
              </template>

              <template v-if="step.llm_trace.output.memory">
                <div class="llm-output-label">Memory</div>
                <div class="llm-output memory">{{ step.llm_trace.output.memory }}</div>
              </template>

              <template v-if="step.llm_trace.output.next_goal">
                <div class="llm-output-label">Next Goal</div>
                <div class="llm-output goal">{{ step.llm_trace.output.next_goal }}</div>
              </template>

              <template v-if="step.llm_trace.output.evaluation">
                <div class="llm-output-label">Evaluation</div>
                <div class="llm-output evaluation">{{ step.llm_trace.output.evaluation }}</div>
              </template>

              <template v-if="step.llm_trace.output.actions?.length">
                <div class="llm-output-label">Actions ({{ step.llm_trace.output.actions.length }})</div>
                <div class="llm-actions">
                  <div v-for="(act, i) in step.llm_trace.output.actions" :key="i" class="llm-action">
                    <span class="llm-action-name">{{ Object.keys(act)[0] }}</span>
                    <pre class="llm-action-args">{{ formatAction(act) }}</pre>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </template>

      <!-- Standard Step Fields -->
      <template v-if="step.thinking">
        <div class="s-label">Thinking</div>
        <div class="s-thinking">{{ step.thinking }}</div>
      </template>
      <template v-if="step.evaluation">
        <div class="s-label">Evaluation</div>
        <div class="s-eval" :class="{ failure: evalClass === 'failure' }">{{ step.evaluation }}</div>
      </template>
      <template v-if="step.memory">
        <div class="s-label">Memory</div>
        <div class="s-memory">{{ step.memory }}</div>
      </template>
      <template v-if="step.next_goal">
        <div class="s-label">Next Goal</div>
        <div class="s-goal">{{ step.next_goal }}</div>
      </template>
      <template v-if="step.actions?.length">
        <div class="s-label">Actions</div>
        <div class="s-actions">{{ actionChips }}</div>
      </template>
      <template v-if="step.url">
        <div class="s-url">URL: {{ step.url }}</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { StepData } from '../types'

const props = defineProps<{
  step: StepData
  filter: string
}>()

defineEmits<{ toggle: [] }>()

const isOpen = ref(false)
const llmOpen = ref(false)

const evalText = computed(() => props.step.evaluation || '')
const evalClass = computed(() => {
  const t = evalText.value.toLowerCase()
  if (t.includes('success')) return 'success'
  if (t.includes('fail') || t.includes('error')) return 'failure'
  return 'neutral'
})

const actionChips = computed(() => {
  return (props.step.actions || []).map((act: any) => {
    const name = Object.keys(act)[0] || 'unknown'
    const params = Object.values(act)[0] || {}
    let paramStr = ''
    if (params.url) paramStr = truncate(params.url, 40)
    else if (params.index !== undefined) paramStr = `#${params.index}`
    else if (params.seconds !== undefined) paramStr = `${params.seconds}s`
    else if (params.text) paramStr = `"${truncate(params.text, 30)}"`
    return `<span class="action-chip"><span class="action-name">${name}</span>${paramStr ? `<span class="action-params">${paramStr}</span>` : ''}</span>`
  }).join('')
})

const visible = computed(() => {
  if (props.filter === 'all') return true
  const tags: string[] = []
  if (props.step.thinking) tags.push('thinking')
  if (props.step.actions?.length) tags.push('actions')
  if ((props.step.evaluation || '').toLowerCase().includes('fail')) tags.push('errors')
  return tags.includes(props.filter)
})

function truncate(str: string, len: number) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

function formatArgs(args: string) {
  if (!args) return ''
  try {
    const obj = JSON.parse(args)
    return JSON.stringify(obj, null, 2)
  } catch {
    return args
  }
}

function formatAction(act: Record<string, any>) {
  const name = Object.keys(act)[0] || 'unknown'
  const params = act[name] || {}
  try {
    return `${name}(${JSON.stringify(params, null, 2)})`
  } catch {
    return `${name}(${JSON.stringify(params)})`
  }
}
</script>

<style scoped>
.step-card {
  margin: 4px 12px 8px;
  border: 1px solid var(--border, #30363d);
  border-radius: 8px;
  overflow: hidden;
  font-size: 12px;
  cursor: pointer;
}

.step-card.hidden { display: none; }

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg2, #161b22);
  border-bottom: 1px solid var(--border, #30363d);
  user-select: none;
}

.step-header:hover { background: var(--bg3, #21262d); }

.step-num {
  font-weight: 700;
  color: var(--accent2, #1f6feb);
  font-size: 11px;
  min-width: 50px;
}

.step-eval-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}

.step-eval-badge.success { background: var(--eval-good, #1a4d2e); color: #3fb950; }
.step-eval-badge.failure { background: var(--eval-bad, #4d1a1a); color: #f85149; }
.step-eval-badge.neutral { background: var(--bg3, #21262d); color: var(--text2, #8b949e); }

.step-actions-summary {
  flex: 1;
  color: var(--text2, #8b949e);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}

.step-url {
  color: var(--text3, #6e7681);
  font-size: 11px;
  font-family: monospace;
}

.llm-trace-badge {
  font-size: 10px;
  color: #8b5cf6;
  padding: 1px 5px;
  border-radius: 8px;
  background: #3b1f5e33;
  border: 1px solid #3b1f5e66;
  cursor: pointer;
}

.step-body {
  display: none;
  padding: 8px 10px;
  background: var(--bg, #0d1117);
}

.step-body.open { display: block; }

.s-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text3, #6e7681);
  margin: 6px 0 3px;
}

.s-thinking {
  background: var(--thinking, #3b1f5e);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  border-left: 3px solid #8b5cf6;
}

.s-eval {
  background: var(--eval-good, #1a4d2e);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  color: #aff5b4;
}

.s-eval.failure { background: var(--eval-bad, #4d1a1a); color: #ffdcd7; }

.s-memory {
  background: var(--mem, #1a3a4d);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  border-left: 3px solid #58a6ff;
}

.s-goal {
  background: var(--goal, #1a3d1a);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  border-left: 3px solid #3fb950;
}

.s-actions { margin-top: 4px; }

:deep(.action-chip) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--accent2-dim, #1f6feb33);
  color: #58a6ff;
  font-size: 11px;
  margin: 2px 4px 2px 0;
  border: 1px solid #1f6feb44;
}

:deep(.action-name) { font-weight: 600; }
:deep(.action-params) { color: #79c0ff; }

.s-url {
  font-size: 11px;
  color: var(--text3, #6e7681);
  padding: 4px 0;
  word-break: break-all;
}

/* ── LLM Trace Panel ─────────────────────────────────────────────────────── */
.llm-panel {
  border: 1px solid #3b1f5e66;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 10px;
  background: #0f0a1e;
}

.llm-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  background: #1a0e3d;
  cursor: pointer;
  user-select: none;
}

.llm-panel-header:hover { background: #22114a; }

.llm-panel-title {
  font-size: 11px;
  font-weight: 700;
  color: #a78bfa;
  letter-spacing: 0.5px;
}

.llm-model {
  font-size: 10px;
  font-weight: 400;
  color: #6e7681;
  margin-left: 6px;
  font-family: monospace;
}

.llm-stats {
  display: flex;
  gap: 8px;
  flex: 1;
}

.llm-token {
  font-size: 10px;
  color: #8b949e;
  font-family: monospace;
  background: #161b22;
  padding: 1px 6px;
  border-radius: 4px;
}

.llm-stop {
  font-size: 10px;
  color: #6e7681;
  font-family: monospace;
}

.llm-toggle {
  font-size: 10px;
  color: #6e7681;
  margin-left: auto;
}

.llm-panel-body {
  padding: 8px 10px;
  max-height: 500px;
  overflow-y: auto;
}

.llm-panel-body::-webkit-scrollbar { width: 4px; }
.llm-panel-body::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }

.llm-section {
  margin-bottom: 12px;
}

.llm-section:last-child { margin-bottom: 0; }

.llm-section-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: #6e7681;
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #30363d33;
}

.llm-msg {
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 6px;
  font-size: 11px;
  border-left: 3px solid;
}

.llm-msg.role-system { background: #1a1a2e; border-color: #f0883e; }
.llm-msg.role-user { background: #1a1a2e; border-color: #58a6ff; }
.llm-msg.role-assistant { background: #1a2a1a; border-color: #3fb950; }
.llm-msg.role-tool { background: #1a2a1a; border-color: #d29922; }

.llm-msg-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 4px;
}

.llm-role {
  font-weight: 700;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.role-system .llm-role { color: #f0883e; }
.role-user .llm-role { color: #58a6ff; }
.role-assistant .llm-role { color: #3fb950; }
.role-tool .llm-role { color: #d29922; }

.llm-images, .llm-tools {
  font-size: 10px;
  color: #6e7681;
}

.llm-msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  color: #c9d1d9;
  max-height: 150px;
  overflow-y: auto;
  font-size: 11px;
}

.llm-tool-calls {
  margin-top: 4px;
}

.llm-tool-call {
  margin-top: 4px;
}

.llm-tool-name {
  font-size: 10px;
  font-weight: 700;
  color: #d29922;
  font-family: monospace;
}

.llm-tool-args {
  font-size: 10px;
  color: #8b949e;
  font-family: monospace;
  background: #161b22;
  padding: 4px 6px;
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre;
  max-height: 80px;
  overflow-y: auto;
  margin-top: 2px;
}

.llm-output-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: #6e7681;
  margin: 6px 0 3px;
}

.llm-output {
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 150px;
  overflow-y: auto;
}

.llm-output.thinking { background: #2d1b4e; border-left: 3px solid #8b5cf6; color: #c4b5fd; }
.llm-output.memory { background: #1a3a4d; border-left: 3px solid #58a6ff; color: #79c0ff; }
.llm-output.goal { background: #1a3d1a; border-left: 3px solid #3fb950; color: #7ee787; }
.llm-output.evaluation { background: #1a4d2e; border-left: 3px solid #3fb950; color: #aff5b4; }

.llm-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.llm-action {
  background: #161b22;
  border-radius: 4px;
  padding: 4px 6px;
}

.llm-action-name {
  font-size: 10px;
  font-weight: 700;
  color: #79c0ff;
  font-family: monospace;
}

.llm-action-args {
  font-size: 10px;
  color: #8b949e;
  font-family: monospace;
  white-space: pre;
  overflow-x: auto;
  max-height: 60px;
  overflow-y: auto;
  margin-top: 2px;
}
</style>
