<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="close">
      <div class="modal">
        <div class="modal-header">
          <div>
            <div class="modal-title">LLM Configuration</div>
            <div class="modal-subtitle">Configure the AI model for the agent</div>
          </div>
          <button class="modal-close" @click="close">&#x2715;</button>
        </div>

        <div class="modal-body">
          <!-- Provider selector -->
          <div class="field-group">
            <label class="field-label">Provider</label>
            <div class="provider-grid">
              <button
                v-for="p in providers"
                :key="p.id"
                class="provider-card"
                :class="{ active: selectedProvider === p.id }"
                @click="selectProvider(p.id)"
                type="button"
              >
                <div class="provider-name">{{ p.name }}</div>
                <div class="provider-desc">{{ p.description }}</div>
                <div class="provider-model">{{ p.default_model }}</div>
              </button>
            </div>
          </div>

          <!-- Config fields -->
          <div class="field-group" v-if="selectedProvider">
            <div class="field-label-row">
              <label class="field-label">Parameters</label>
              <button class="btn-link" @click="resetToDefaults" type="button">Reset to defaults</button>
            </div>

            <!-- API Key -->
            <div class="field-row">
              <div class="field">
                <label class="field-name">API Key</label>
                <div class="input-wrap">
                  <input
                    :type="showApiKey ? 'text' : 'password'"
                    v-model="form.api_key"
                    placeholder="sk-..."
                    autocomplete="off"
                  />
                  <button class="input-toggle" @click="showApiKey = !showApiKey" type="button">
                    {{ showApiKey ? '🙈' : '👁' }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Model -->
            <div class="field-row">
              <div class="field">
                <label class="field-name">Model</label>
                <input type="text" v-model="form.model" :placeholder="defaultModel" />
              </div>
            </div>

            <!-- Base URL (conditional) -->
            <div class="field-row" v-if="hasField('base_url') || hasField('host')">
              <div class="field">
                <label class="field-name">{{ selectedProvider === 'ollama' ? 'Ollama Host' : 'Base URL' }}</label>
                <input
                  type="text"
                  v-model="form.base_url"
                  :placeholder="selectedProvider === 'ollama' ? 'http://localhost:11434' : 'https://api.example.com/v1'"
                />
              </div>
            </div>

            <!-- Temperature -->
            <div class="field-row">
              <div class="field">
                <label class="field-name">Temperature <span class="field-hint">{{ form.temperature ?? '' }}</span></label>
                <input
                  type="range"
                  min="0" max="2" step="0.1"
                  v-model.number="form.temperature"
                  class="range-input"
                />
                <div class="range-labels"><span>Precise</span><span>Creative</span></div>
              </div>
            </div>

            <!-- Top P -->
            <div class="field-row" v-if="hasField('top_p')">
              <div class="field">
                <label class="field-name">Top P <span class="field-hint">{{ form.top_p ?? '' }}</span></label>
                <input type="range" min="0" max="1" step="0.05" v-model.number="form.top_p" class="range-input" />
              </div>
            </div>

            <!-- Max Tokens -->
            <div class="field-row" v-if="hasField('max_tokens')">
              <div class="field">
                <label class="field-name">Max Output Tokens</label>
                <input type="number" v-model.number="form.max_tokens" placeholder="4096" min="1" />
              </div>
            </div>

            <!-- Timeout -->
            <div class="field-row" v-if="hasField('timeout')">
              <div class="field">
                <label class="field-name">Timeout (seconds)</label>
                <input type="number" v-model.number="form.timeout" placeholder="120" min="1" />
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <div class="modal-footer-left">
            <span v-if="saveStatus" class="save-status" :class="saveStatus">{{ saveStatusMsg }}</span>
          </div>
          <div class="modal-footer-right">
            <button class="btn" @click="close" type="button">Cancel</button>
            <button class="btn btn-primary" @click="save" :disabled="saving" type="button">
              {{ saving ? 'Saving...' : 'Save Configuration' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed } from 'vue'
import { api } from '../api'
import type { LlmProvider, LlmConfig } from '../types'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  close: []
  saved: [config: LlmConfig]
}>()

const providers = ref<LlmProvider[]>([])
const selectedProvider = ref('')
const saving = ref(false)
const saveStatus = ref('')
const saveStatusMsg = ref('')
const showApiKey = ref(false)

const form = reactive({
  api_key: '',
  model: '',
  base_url: '',
  temperature: null as number | null,
  top_p: null as number | null,
  max_tokens: null as number | null,
  timeout: null as number | null,
})

function hasField(field: string): boolean {
  const p = providers.value.find(p => p.id === selectedProvider.value)
  return p?.fields.includes(field) ?? false
}

const defaultModel = computed(() => {
  const p = providers.value.find(p => p.id === selectedProvider.value)
  return p?.default_model ?? ''
})

async function load() {
  try {
    const [provRes, cfgRes] = await Promise.all([
      api.getProviders(),
      api.getLlmConfig(),
    ])
    providers.value = provRes.providers

    if (cfgRes.config) {
      selectedProvider.value = cfgRes.config.provider
      applyConfig(cfgRes.config)
    } else {
      // Default to deepseek
      selectedProvider.value = 'deepseek'
    }
  } catch (e) {
    console.error('Failed to load config:', e)
  }
}

function applyConfig(cfg: LlmConfig) {
  form.api_key = cfg.api_key ?? ''
  form.model = cfg.model ?? ''
  form.base_url = cfg.base_url ?? ''
  form.temperature = cfg.temperature ?? null
  form.top_p = cfg.top_p ?? null
  form.max_tokens = cfg.max_tokens ?? null
  form.timeout = cfg.timeout ?? null
}

function resetToDefaults() {
  const p = providers.value.find(p => p.id === selectedProvider.value)
  if (!p) return
  form.model = p.default_model
  form.base_url = ''
  form.temperature = null
  form.top_p = null
  form.max_tokens = null
  form.timeout = null
  form.api_key = ''
}

function selectProvider(id: string) {
  selectedProvider.value = id
  resetToDefaults()
}

async function save() {
  saving.value = true
  saveStatus.value = ''
  try {
    const config: LlmConfig = {
      provider: selectedProvider.value,
      extra: {},
    }
    if (form.api_key) config.api_key = form.api_key
    if (form.model) config.model = form.model
    if (form.base_url) config.base_url = form.base_url
    if (form.temperature !== null) config.temperature = form.temperature
    if (form.top_p !== null) config.top_p = form.top_p
    if (form.max_tokens !== null) config.max_tokens = form.max_tokens
    if (form.timeout !== null) config.timeout = form.timeout

    const res = await api.updateLlmConfig(config)
    saveStatus.value = 'success'
    saveStatusMsg.value = 'Configuration saved'
    emit('saved', res.config)
    setTimeout(() => {
      saveStatus.value = ''
    }, 3000)
  } catch (e: any) {
    saveStatus.value = 'error'
    saveStatusMsg.value = e.message || 'Failed to save'
  } finally {
    saving.value = false
  }
}

function close() {
  saveStatus.value = ''
  emit('close')
}

watch(() => props.visible, (v) => {
  if (v) {
    load()
  }
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal {
  background: var(--bg2, #161b22);
  border: 1px solid var(--border, #30363d);
  border-radius: 12px;
  width: 680px;
  max-width: 95vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border, #30363d);
  flex-shrink: 0;
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text, #e6edf3);
}

.modal-subtitle {
  font-size: 12px;
  color: var(--text3, #6e7681);
  margin-top: 4px;
}

.modal-close {
  background: none;
  border: none;
  color: var(--text3, #6e7681);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.modal-close:hover {
  color: var(--text, #e6edf3);
  background: var(--bg3, #21262d);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
}

.modal-body::-webkit-scrollbar { width: 6px; }
.modal-body::-webkit-scrollbar-track { background: transparent; }
.modal-body::-webkit-scrollbar-thumb { background: var(--border, #30363d); border-radius: 3px; }

.field-group {
  margin-bottom: 20px;
}

.field-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text3, #6e7681);
  display: block;
  margin-bottom: 8px;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.field-label-row .field-label {
  margin-bottom: 0;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.provider-card {
  border: 1px solid var(--border, #30363d);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--bg, #0d1117);
  color: var(--text2, #8b949e);
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
  font-family: inherit;
}

.provider-card:hover {
  border-color: var(--accent2, #1f6feb);
  background: var(--bg3, #21262d);
}

.provider-card.active {
  border-color: var(--accent2, #1f6feb);
  background: rgba(31, 111, 235, 0.1);
  color: var(--text, #e6edf3);
}

.provider-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #e6edf3);
  margin-bottom: 2px;
}

.provider-desc {
  font-size: 10px;
  color: var(--text3, #6e7681);
  line-height: 1.3;
  margin-bottom: 4px;
}

.provider-model {
  font-size: 10px;
  font-family: monospace;
  color: var(--accent2, #1f6feb);
  background: rgba(31, 111, 235, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
  display: inline-block;
}

.field-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}

.field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-name {
  font-size: 12px;
  color: var(--text2, #8b949e);
}

.field-hint {
  color: var(--accent2, #1f6feb);
  font-family: monospace;
}

.input-wrap {
  position: relative;
  display: flex;
}

.input-wrap input {
  flex: 1;
  padding-right: 36px;
}

.input-toggle {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 4px;
}

input[type="text"],
input[type="password"],
input[type="number"] {
  width: 100%;
  background: var(--bg, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
  color: var(--text, #e6edf3);
  font-family: 'Segoe UI', 'SF Mono', Consolas, monospace;
  font-size: 13px;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.15s;
}

input[type="text"]:focus,
input[type="password"]:focus,
input[type="number"]:focus {
  border-color: var(--accent2, #1f6feb);
}

input[type="text"]::placeholder,
input[type="password"]::placeholder,
input[type="number"]::placeholder {
  color: var(--text3, #6e7681);
}

.range-input {
  width: 100%;
  height: 4px;
  accent-color: var(--accent2, #1f6feb);
  cursor: pointer;
}

.range-labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text3, #6e7681);
  margin-top: 2px;
}

.btn-link {
  background: none;
  border: none;
  color: var(--accent2, #1f6feb);
  font-size: 11px;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}

.btn-link:hover {
  text-decoration: underline;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-top: 1px solid var(--border, #30363d);
  flex-shrink: 0;
}

.modal-footer-left {
  flex: 1;
}

.modal-footer-right {
  display: flex;
  gap: 8px;
}

.save-status {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
}

.save-status.success {
  background: rgba(35, 134, 54, 0.2);
  color: #3fb950;
  border: 1px solid #238636;
}

.save-status.error {
  background: rgba(218, 54, 51, 0.2);
  color: #f85149;
  border: 1px solid #da3633;
}

.btn {
  padding: 7px 16px;
  border-radius: 6px;
  border: 1px solid var(--border, #30363d);
  background: var(--bg3, #21262d);
  color: var(--text, #e6edf3);
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: background 0.15s;
}

.btn:hover {
  background: #30363d;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: #238636;
  border-color: #238636;
  color: #fff;
}

.btn-primary:hover {
  background: #2ea043;
}

.btn-primary:disabled {
  background: #238636;
  opacity: 0.5;
}
</style>
