<template>
  <div id="app-root">
    <!-- Top Bar -->
    <header id="topbar">
      <h1>Browser-Use <span>/ Agent Control</span></h1>
      <button class="topbar-btn" @click="openLlmConfig" :title="'Configure LLM: ' + (currentModel || 'not set')">
        <span class="topbar-icon">&#9881;</span>
        <span class="topbar-label">{{ currentModel || 'Set Model' }}</span>
      </button>
      <span id="status-badge" class="status-badge">{{ status }}</span>
      <div class="spacer"></div>
      <span id="step-counter">steps: {{ stepCount }}</span>
    </header>

    <!-- Main -->
    <main id="main">
      <!-- Left: Task + Log -->
      <section id="left">
        <div id="task-section">
          <label>Task</label>
          <textarea
            id="task-input"
            v-model="taskInput"
            placeholder="Enter your task here...
Example: Go to https://example.com and search for &quot;browser automation&quot;"
          ></textarea>
          <div id="task-actions">
            <button id="btn-execute" class="btn btn-primary" @click="executeTask" :disabled="taskRunning">
              &#9654; Execute
            </button>
            <button id="btn-stop" class="btn btn-danger" @click="stopTask" v-if="taskRunning">
              &#9632; Stop
            </button>
            <div class="spacer"></div>
            <span class="task-status-text">{{ taskStatusText }}</span>
          </div>
        </div>

        <div id="log-panel">
          <div id="log-header">
            <span>Execution Log</span>
            <div class="filter-group">
              <button
                v-for="f in filters"
                :key="f.id"
                class="log-filter"
                :class="{ active: currentFilter === f.id }"
                @click="currentFilter = f.id"
              >{{ f.label }}</button>
            </div>
            <div class="spacer"></div>
            <button id="log-clear" @click="clearLog">Clear</button>
          </div>
          <div id="log-content">
            <div v-if="steps.length === 0" id="log-empty">
              <div class="empty-icon">&#128752;</div>
              <div>Write a task above and click Execute</div>
              <div class="empty-hint">Model thinking and actions will appear here</div>
            </div>
            <StepCard
              v-for="s in steps"
              :key="s.step"
              :step="s"
              :filter="currentFilter"
              @toggle="toggleStep(s.step)"
            />
          </div>
        </div>
      </section>

      <!-- Right: Skills + Learned Actions -->
      <aside id="right">
        <div class="panel-tabs">
          <button
            class="panel-tab"
            :class="{ active: rightTab === 'skills' }"
            @click="rightTab = 'skills'"
          >Skills</button>
          <button
            class="panel-tab"
            :class="{ active: rightTab === 'learned' }"
            @click="rightTab = 'learned'; loadLearnedActions()"
          >Learned</button>
        </div>

        <!-- Skills Panel -->
        <template v-if="rightTab === 'skills'">
          <div id="skills-header">
            <span>Skills</span>
            <span id="skills-count" class="count-badge">{{ skills.length }}</span>
            <div class="spacer"></div>
            <button class="btn-sm" @click="loadSkills">&#8635;</button>
          </div>
          <div id="selected-skills-bar">
            <span
              v-for="id in selectedSkillIds"
              :key="id"
              class="selected-chip"
            >
              {{ getSkillName(id) }}
              <span class="remove" @click="deselectSkill(id)">&#215;</span>
            </span>
          </div>
          <div id="skills-list">
            <div v-if="skills.length === 0" class="empty-panel">
              No skills yet.<br>Complete successful steps to auto-generate skills.
            </div>
            <SkillCard
              v-for="s in skills"
              :key="s.id"
              :skill="s"
              :selected="selectedSkillIds.has(s.id)"
              @toggle-select="toggleSkillSelect(s.id)"
              @delete="deleteSkill(s.id)"
            />
          </div>
          <div id="compose-bar">
            <button class="btn btn-primary btn-sm" @click="composeFromSelected" :disabled="selectedSkillIds.size === 0">
              Use Selected
            </button>
            <input
              id="compose-task"
              :value="composedTask"
              readonly
              @click="$event.target?.select()"
              placeholder="Selected skills will appear here..."
            />
          </div>
        </template>

        <!-- Learned Actions Panel -->
        <template v-else>
          <div id="skills-header">
            <span>Learned Actions</span>
            <span id="skills-count" class="count-badge">{{ learnedActions.length }}</span>
            <div class="spacer"></div>
            <button class="btn-sm" @click="loadLearnedActions">&#8635;</button>
          </div>
          <div id="skills-list">
            <div v-if="learnedActions.length === 0" class="empty-panel">
              No learned actions yet.<br>When the agent asks for help, your clicks are saved here.
            </div>
            <div
              v-for="(action, key) in learnedActions"
              :key="key"
              class="learned-card"
            >
              <div class="learned-url">{{ action.url_pattern || '(any page)' }}</div>
              <div class="learned-btn">Click: {{ action.button_text }}</div>
              <div class="learned-meta">
                <span class="learned-target">{{ action.target_url || '—' }}</span>
                <button class="learned-delete" @click="deleteLearned(key)" title="Delete">&#215;</button>
              </div>
            </div>
          </div>
        </template>
      </aside>
    </main>

    <!-- Modals -->
    <LlmConfigModal
      :visible="llmConfigVisible"
      @close="llmConfigVisible = false"
      @saved="onLlmConfigSaved"
    />
    <HumanHelpModal
      :visible="humanHelpVisible"
      :session-id="currentSessionId || ''"
      :question="humanHelpQuestion"
      :url="humanHelpUrl"
      @close="humanHelpVisible = false"
      @learned="onHumanHelpLearned"
    />

    <!-- Toast -->
    <div id="toast" :class="toastClass">{{ toastMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from './api'
import type { StepData, Skill, LearnedAction, HumanHelpPayload } from './types'
import LlmConfigModal from './components/LlmConfigModal.vue'
import HumanHelpModal from './components/HumanHelpModal.vue'
import StepCard from './components/StepCard.vue'
import SkillCard from './components/SkillCard.vue'

// ── State ──────────────────────────────────────────────────────────────────
const currentSessionId = ref<string | null>(null)
const taskInput = ref('')
const taskRunning = ref(false)
const status = ref('idle')
const stepCount = ref(0)
const taskStatusText = ref('')
const steps = ref<StepData[]>([])
const currentFilter = ref('all')
const openSteps = ref<Set<number>>(new Set())

// Skills
const skills = ref<Skill[]>([])
const selectedSkillIds = ref<Set<string>>(new Set())
const composedTask = ref('')
const rightTab = ref('skills')

// LLM Config
const llmConfigVisible = ref(false)
const currentModel = ref('')

// Human Help
const humanHelpVisible = ref(false)
const humanHelpQuestion = ref('')
const humanHelpUrl = ref('')

// Toast
const toastMsg = ref('')
const toastTimer = ref<number | null>(null)

// SSE
let evtSource: EventSource | null = null

const filters = [
  { id: 'all', label: 'All' },
  { id: 'thinking', label: 'Thinking' },
  { id: 'actions', label: 'Actions' },
  { id: 'errors', label: 'Errors' },
]

// ── Computed ────────────────────────────────────────────────────────────────
const toastClass = computed(() => {
  if (toastMsg.value.startsWith('Error') || toastMsg.value.includes('failed')) return 'show error'
  if (toastMsg.value.includes('saved') || toastMsg.value.includes('success') || toastMsg.value.includes('Generated')) return 'show success'
  return 'show'
})

// ── Task Execution ─────────────────────────────────────────────────────────
async function executeTask() {
  const task = taskInput.value.trim()
  if (!task) { toast('Please enter a task', 'error'); return }
  if (taskRunning.value) { toast('A task is already running', 'error'); return }

  // Create session
  let sessionId: string
  try {
    const data = await api.createSession()
    sessionId = data.session_id
    currentSessionId.value = sessionId
  } catch (e: any) {
    toast('Cannot create session: ' + e.message, 'error')
    return
  }

  // Start SSE
  startSSE(sessionId)

  status.value = 'running'
  taskRunning.value = true
  taskStatusText.value = 'Agent is thinking...'
  stepCount.value = 0
  steps.value = []
  document.getElementById('log-empty')?.remove()

  try {
    await api.executeTask(sessionId, task)
  } catch (e: any) {
    toast('Failed to start task: ' + e.message, 'error')
    stopSSE()
    status.value = 'idle'
    taskRunning.value = false
  }
}

async function stopTask() {
  if (!currentSessionId.value) return
  await api.stopSession(currentSessionId.value)
  taskStatusText.value = 'Stopping...'
}

// ── SSE ─────────────────────────────────────────────────────────────────────
function startSSE(sessionId: string) {
  stopSSE()
  evtSource = new EventSource(`/events/${sessionId}`)
  evtSource.addEventListener('step', (e) => {
    try { onStep(JSON.parse(e.data)) } catch(err) { console.error('step parse error:', err) }
  })
  evtSource.addEventListener('llm_trace', (e) => {
    try { onLlmTrace(JSON.parse(e.data)) } catch(err) { console.error('llm_trace parse error:', err) }
  })
  evtSource.addEventListener('done', (e) => {
    try { onDone(JSON.parse(e.data)) } catch(err) { console.error('done parse error:', err) }
  })
  evtSource.addEventListener('status', (e) => {
    try { onStatus(JSON.parse(e.data)) } catch(err) { console.error('status parse error:', err) }
  })
  evtSource.addEventListener('error', (e) => {
    try { onError(JSON.parse(e.data)) } catch(err) { console.error('error parse error:', err) }
  })
  evtSource.addEventListener('agent_info', (e) => {
    try { onAgentInfo(JSON.parse(e.data)) } catch(err) { console.error('agent_info parse error:', err) }
  })
  evtSource.addEventListener('human_help', (e) => {
    try { onHumanHelp(JSON.parse(e.data)) } catch(err) { console.error('human_help parse error:', err) }
  })
  evtSource.addEventListener('human_help_result', (e) => {
    try { onHumanHelpResult(JSON.parse(e.data)) } catch(err) { console.error('human_help_result parse error:', err) }
  })
  evtSource.onerror = (e) => {
    console.warn('SSE connection error, waiting for reconnect...', e)
  }
}

function stopSSE() {
  if (evtSource) {
    evtSource.close()
    evtSource = null
  }
}

function onAgentInfo(data: any) {
  currentModel.value = data.model || ''
}

function onStatus(data: any) {
  if (data.status === 'running') {
    status.value = 'running'
    taskRunning.value = true
    taskStatusText.value = 'Agent is thinking...'
  } else if (data.status === 'done' || data.status === 'stopping') {
    status.value = 'done'
    taskRunning.value = false
    taskStatusText.value = 'Done'
    stopSSE()
    loadSkills()
  }
}

function onStep(data: any) {
  stepCount.value++
  steps.value.push(data)
  scrollLog()
}

function onLlmTrace(data: any) {
  // Attach LLM trace to the most recent step
  if (steps.value.length > 0) {
    steps.value[steps.value.length - 1].llm_trace = data
  }
}

function onDone(data: any) {
  status.value = data.success ? 'done' : 'done'
  taskRunning.value = false
  taskStatusText.value = data.success ? 'Success' : 'Ended'
  stopSSE()

  const logContent = document.getElementById('log-content')
  if (logContent) {
    const div = document.createElement('div')
    div.className = `log-meta ${data.success ? 'success' : ''}`
    div.innerHTML = `<strong>${data.success ? '&#10004; Task completed' : '&#9888; Task ended'}</strong> — ${data.final_result || ''} (${data.steps_taken} steps)`
    logContent.appendChild(div)
    scrollLog()
  }

  if (data.new_skills?.length > 0) {
    toast(`Generated ${data.new_skills.length} skill(s)`, 'success')
  }

  loadSkills()
}

function onError(data: any) {
  status.value = 'error'
  taskRunning.value = false
  taskStatusText.value = 'Error'
  const logContent = document.getElementById('log-content')
  if (logContent) {
    const div = document.createElement('div')
    div.className = 'log-meta error'
    div.textContent = 'Error: ' + data.message
    logContent.appendChild(div)
    scrollLog()
  }
  stopSSE()
}

function onHumanHelp(data: any) {
  humanHelpQuestion.value = data.question || 'Agent needs help'
  humanHelpUrl.value = data.url || ''
  humanHelpVisible.value = true
}

function onHumanHelpResult(data: any) {
  humanHelpVisible.value = false
  toast('Human help received, continuing...', 'success')
}

function onHumanHelpLearned() {
  loadLearnedActions()
  toast('Learned! Agent will remember this next time.', 'success')
}

function scrollLog() {
  const lc = document.getElementById('log-content')
  if (lc) lc.scrollTop = lc.scrollHeight
}

// ── Steps ───────────────────────────────────────────────────────────────────
function toggleStep(n: number) {
  if (openSteps.value.has(n)) openSteps.value.delete(n)
  else openSteps.value.add(n)
}

function clearLog() {
  steps.value = []
  stepCount.value = 0
  const el = document.getElementById('log-content')
  if (el) {
    el.innerHTML = `
      <div id="log-empty">
        <div class="empty-icon">&#128752;</div>
        <div>Write a task above and click Execute</div>
        <div class="empty-hint">Model thinking and actions will appear here</div>
      </div>`
  }
}

// ── Skills ──────────────────────────────────────────────────────────────────
async function loadSkills() {
  try {
    const data = await api.getSkills()
    skills.value = data.skills || []
  } catch (e) { console.error(e) }
}

function toggleSkillSelect(id: string) {
  if (selectedSkillIds.value.has(id)) selectedSkillIds.value.delete(id)
  else selectedSkillIds.value.add(id)
}

function deselectSkill(id: string) {
  selectedSkillIds.value.delete(id)
}

function getSkillName(id: string) {
  const s = skills.value.find(s => s.id === id)
  return s?.name || s?.description || id
}

async function deleteSkill(id: string) {
  if (!confirm('Delete this skill?')) return
  try {
    await api.deleteSkill(id)
    selectedSkillIds.value.delete(id)
    loadSkills()
    toast('Skill deleted', 'success')
  } catch (e) { toast('Failed to delete', 'error') }
}

async function composeFromSelected() {
  const ids = Array.from(selectedSkillIds.value)
  if (ids.length === 0) { toast('Select skills first', 'error'); return }
  try {
    const data = await api.composeTask(ids)
    composedTask.value = data.task || ''
    taskInput.value = data.task || ''
    toast(`Composed task from ${ids.length} skill(s)`, 'success')
  } catch (e) { toast('Failed to compose task', 'error') }
}

// ── Learned Actions ─────────────────────────────────────────────────────────
const learnedActions = ref<LearnedAction[]>([])

async function loadLearnedActions() {
  try {
    const data = await api.getLearnedActions()
    learnedActions.value = data.learned_actions || []
  } catch (e) { console.error(e) }
}

async function deleteLearned(key: string) {
  try {
    await api.deleteLearnedAction(key)
    loadLearnedActions()
    toast('Learned action deleted', 'success')
  } catch (e) { toast('Failed to delete', 'error') }
}

// ── LLM Config ───────────────────────────────────────────────────────────────
function openLlmConfig() {
  llmConfigVisible.value = true
}

async function onLlmConfigSaved(config: any) {
  currentModel.value = config.provider + (config.model ? ':' + config.model : '')
  toast(`Model set to ${currentModel.value}`, 'success')
  llmConfigVisible.value = false
}

// ── Toast ────────────────────────────────────────────────────────────────────
function toast(msg: string, type: 'success' | 'error' | '' = '') {
  toastMsg.value = type === 'error' ? 'Error: ' + msg : msg
  if (toastTimer.value) clearTimeout(toastTimer.value)
  toastTimer.value = window.setTimeout(() => { toastMsg.value = '' }, 3000)
}

// ── Init ─────────────────────────────────────────────────────────────────────
onMounted(() => {
  loadSkills()
  loadLlmConfig()
})

onUnmounted(() => {
  stopSSE()
})

async function loadLlmConfig() {
  try {
    const data = await api.getLlmConfig()
    if (data.config) {
      currentModel.value = data.config.provider + (data.config.model ? ':' + data.config.model : '')
    }
  } catch (e) { console.error(e) }
}
</script>

<style>
/* ── Global Reset & CSS Variables ───────────────────────────────────────────── */
:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #6e7681;
  --accent: #238636;
  --accent2: #1f6feb;
  --accent2-dim: #1f6feb33;
  --danger: #da3633;
  --warn: #d29922;
  --thinking: #3b1f5e;
  --eval-good: #1a4d2e;
  --eval-bad: #4d1a1a;
  --mem: #1a3a4d;
  --goal: #1a3d1a;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, #app-root {
  height: 100%;
  overflow: hidden;
}

body {
  font-family: 'Segoe UI', 'SF Mono', Consolas, monospace;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  line-height: 1.5;
}

/* ── Top Bar ───────────────────────────────────────────────────────────────── */
#topbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  height: 44px;
}

#topbar h1 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0.5px;
  white-space: nowrap;
}

#topbar h1 span { color: var(--text3); font-weight: 400; }

.topbar-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--text2);
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
  white-space: nowrap;
  overflow: hidden;
  max-width: 220px;
}

.topbar-btn:hover {
  border-color: var(--accent2);
  color: var(--text);
  background: var(--bg3);
}

.topbar-icon { font-size: 12px; }
.topbar-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
}

.spacer { flex: 1; }

.status-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 12px;
  background: var(--bg3);
  border: 1px solid var(--border);
  color: var(--text2);
  font-family: monospace;
  white-space: nowrap;
}

.status-badge.running { background: #1a4d2e; border-color: var(--accent); color: #3fb950; }
.status-badge.done { background: var(--bg3); border-color: var(--accent); color: #3fb950; }
.status-badge.error { background: #4d1a1a; border-color: var(--danger); color: #f85149; }

#step-counter {
  font-size: 11px;
  color: var(--text3);
  font-family: monospace;
  white-space: nowrap;
}

/* ── Main Layout ───────────────────────────────────────────────────────────── */
#main {
  display: flex;
  height: calc(100vh - 44px);
  overflow: hidden;
}

/* ── Left Panel ────────────────────────────────────────────────────────────── */
#left {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  min-width: 0;
}

#task-section {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

#task-section label {
  font-size: 11px;
  color: var(--text3);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  display: block;
  margin-bottom: 6px;
}

#task-input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: 'Segoe UI', monospace;
  font-size: 13px;
  padding: 8px 10px;
  resize: vertical;
  min-height: 80px;
  outline: none;
  transition: border-color 0.15s;
}

#task-input:focus { border-color: var(--accent2); }
#task-input::placeholder { color: var(--text3); }

#task-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  align-items: center;
}

.task-status-text {
  font-size: 11px;
  color: var(--text3);
  align-self: center;
}

/* ── Log Panel ─────────────────────────────────────────────────────────────── */
#log-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#log-header {
  display: flex;
  align-items: center;
  padding: 6px 16px;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  gap: 8px;
  flex-shrink: 0;
}

#log-header > span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text3);
  white-space: nowrap;
}

.filter-group { display: flex; gap: 4px; }

.log-filter {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text2);
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.log-filter:hover { background: var(--bg3); }
.log-filter.active {
  background: var(--accent2-dim);
  border-color: var(--accent2);
  color: #58a6ff;
}

#log-clear {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text3);
  cursor: pointer;
  font-family: inherit;
}

#log-clear:hover { color: var(--text); border-color: var(--text3); }

#log-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  scroll-behavior: smooth;
}

#log-content::-webkit-scrollbar { width: 6px; }
#log-content::-webkit-scrollbar-track { background: transparent; }
#log-content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

#log-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text3);
  font-size: 13px;
  gap: 8px;
}

.empty-icon { font-size: 36px; opacity: 0.3; }
.empty-hint { font-size: 11px; margin-top: 4px; }

.log-meta {
  padding: 6px 16px;
  font-size: 12px;
  color: var(--text3);
  border-bottom: 1px solid var(--border);
}

.log-meta.success { color: #3fb950; }
.log-meta.error { color: #f85149; }

/* ── Right Panel ───────────────────────────────────────────────────────────── */
#right {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg2);
  overflow: hidden;
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.panel-tab {
  flex: 1;
  padding: 8px;
  background: none;
  border: none;
  color: var(--text3);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.panel-tab:hover { color: var(--text2); }
.panel-tab.active {
  color: var(--text);
  border-bottom-color: var(--accent2);
}

#skills-header {
  display: flex;
  align-items: center;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 8px;
}

#skills-header > span {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text3);
}

.count-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--bg3);
  color: var(--text3);
  font-family: monospace;
}

#selected-skills-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 14px 0;
  min-height: 20px;
}

.selected-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--accent2-dim);
  color: #58a6ff;
  font-size: 10px;
  border: 1px solid #1f6feb44;
}

.selected-chip .remove {
  cursor: pointer;
  color: #79c0ff;
  font-size: 12px;
}

.selected-chip .remove:hover { color: #f85149; }

#skills-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

#skills-list::-webkit-scrollbar { width: 4px; }
#skills-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.empty-panel {
  text-align: center;
  padding: 40px 16px;
  color: var(--text3);
  font-size: 12px;
  line-height: 1.6;
}

/* Learned Action Cards */
.learned-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}

.learned-url {
  font-size: 10px;
  color: var(--text3);
  font-family: monospace;
  word-break: break-all;
  margin-bottom: 4px;
}

.learned-btn {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}

.learned-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.learned-target {
  font-size: 10px;
  color: var(--accent2);
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.learned-delete {
  background: none;
  border: none;
  color: var(--text3);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  border-radius: 3px;
}

.learned-delete:hover { background: #da363322; color: var(--danger); }

/* Compose bar */
#compose-bar {
  padding: 8px 14px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  display: flex;
  gap: 6px;
  align-items: center;
}

#compose-task {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  padding: 5px 8px;
  outline: none;
  cursor: text;
}

#compose-task:focus { border-color: var(--accent2); }

/* ── Buttons ───────────────────────────────────────────────────────────────── */
.btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
  white-space: nowrap;
}

.btn:hover { background: #30363d; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.btn-primary:hover { background: #2ea043; }
.btn-danger {
  background: transparent;
  border-color: var(--danger);
  color: var(--danger);
}
.btn-danger:hover { background: #da363322; }

.btn-sm {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg3);
  color: var(--text2);
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.btn-sm:hover { background: #30363d; color: var(--text); }

/* ── Toast ──────────────────────────────────────────────────────────────────── */
#toast {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: var(--bg3);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 13px;
  color: var(--text);
  z-index: 2000;
  transform: translateY(100px);
  opacity: 0;
  transition: transform 0.3s, opacity 0.3s;
  max-width: 320px;
  pointer-events: none;
}

#toast.show {
  transform: translateY(0);
  opacity: 1;
}

#toast.success { border-color: var(--accent); color: #3fb950; }
#toast.error { border-color: var(--danger); color: #f85149; }
</style>
