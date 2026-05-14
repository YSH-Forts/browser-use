<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="dismiss">
      <div class="modal">
        <div class="modal-header">
          <div class="header-content">
            <div class="modal-title">&#128679; Agent Needs Help</div>
            <div class="modal-subtitle">{{ question }}</div>
          </div>
        </div>

        <div class="modal-body">
          <div class="info-row">
            <span class="info-label">Current URL:</span>
            <span class="info-value url">{{ url }}</span>
          </div>

          <div class="instructions">
            Please click on the element the agent needs, then click Submit below.
          </div>

          <div class="field-group">
            <label class="field-label">What did you click?</label>
            <div class="field-row">
              <div class="field">
                <label class="field-name">Button / Element Text</label>
                <input type="text" v-model="buttonText" placeholder="e.g., Sign In, Submit, Continue..." autofocus />
              </div>
            </div>
            <div class="field-row">
              <div class="field">
                <label class="field-name">Where did it go? (URL after click, optional)</label>
                <input type="text" v-model="resultUrl" placeholder="https://..." />
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-danger" @click="dismiss" type="button">Skip</button>
          <button class="btn btn-primary" @click="submit" :disabled="!buttonText.trim()" type="button">
            Submit &amp; Learn
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api'
import type { HumanHelpPayload } from '../types'

const props = defineProps<{
  visible: boolean
  sessionId: string
  question: string
  url: string
}>()

const emit = defineEmits<{
  close: []
  learned: []
}>()

const buttonText = ref('')
const resultUrl = ref('')

async function submit() {
  try {
    await api.submitHumanHelp(props.sessionId, {
      button_text: buttonText.value.trim(),
      url_on_click: resultUrl.value.trim(),
      description: props.question,
      question: props.question,
    })
    emit('learned')
    emit('close')
    buttonText.value = ''
    resultUrl.value = ''
  } catch (e) {
    console.error('Failed to submit human help:', e)
  }
}

function dismiss() {
  emit('close')
  buttonText.value = ''
  resultUrl.value = ''
}
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
  width: 560px;
  max-width: 95vw;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}

.modal-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border, #30363d);
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: #d29922;
}

.modal-subtitle {
  font-size: 13px;
  color: var(--text2, #8b949e);
  margin-top: 6px;
  line-height: 1.5;
}

.modal-body {
  padding: 16px 24px;
}

.info-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 12px;
}

.info-label {
  color: var(--text3, #6e7681);
  flex-shrink: 0;
}

.info-value {
  color: var(--text2, #8b949e);
}

.info-value.url {
  font-family: monospace;
  word-break: break-all;
  color: var(--accent2, #1f6feb);
}

.instructions {
  background: rgba(210, 153, 34, 0.1);
  border: 1px solid rgba(210, 153, 34, 0.3);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  color: #d29922;
  margin-bottom: 16px;
}

.field-group {
  margin-bottom: 4px;
}

.field-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text3, #6e7681);
  display: block;
  margin-bottom: 8px;
}

.field-row {
  margin-bottom: 10px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-name {
  font-size: 12px;
  color: var(--text2, #8b949e);
}

input[type="text"] {
  width: 100%;
  background: var(--bg, #0d1117);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
  color: var(--text, #e6edf3);
  font-family: 'Segoe UI', monospace;
  font-size: 13px;
  padding: 7px 10px;
  outline: none;
  transition: border-color 0.15s;
}

input[type="text"]:focus {
  border-color: var(--accent2, #1f6feb);
}

input[type="text"]::placeholder {
  color: var(--text3, #6e7681);
}

.modal-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding: 12px 24px;
  border-top: 1px solid var(--border, #30363d);
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

.btn-danger {
  border-color: #da3633;
  color: #da3633;
}

.btn-danger:hover {
  background: rgba(218, 54, 51, 0.1);
}
</style>
