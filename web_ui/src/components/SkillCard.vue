<template>
  <div class="skill-card" :class="{ selected }" @click="$emit('toggleSelect', skill.id)">
    <button class="skill-delete" @click.stop="$emit('delete', skill.id)" title="Delete">&#215;</button>
    <div class="skill-name">{{ skill.name || skill.description?.slice(0, 50) || 'Untitled' }}</div>
    <div class="skill-desc" v-if="skill.description && skill.description.length > 60">
      {{ skill.description.slice(0, 80) }}...
    </div>
    <div class="skill-meta">
      <span class="skill-type" :class="skill.action_type">{{ skill.action_type || 'unknown' }}</span>
      <span v-if="skill.action_type === 'workflow_chain'" class="skill-chain-hint">
        {{ chainLength }} step{{ chainLength !== 1 ? 's' : '' }}
      </span>
      <span class="skill-outcome" :class="skill.params?.outcome">{{ skill.params?.outcome || '' }}</span>
      <span class="skill-date">{{ skill.created_at?.slice(0, 10) || '' }}</span>
    </div>
    <div v-if="selected" class="selected-indicator">&#10003;</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Skill } from '../types'

const props = defineProps<{
  skill: Skill
  selected: boolean
}>()

defineEmits<{
  toggleSelect: [id: string]
  delete: [id: string]
}>()

const chainLength = computed(() => {
  if (props.skill.action_type === 'workflow_chain') {
    const steps = props.skill.params?.steps || []
    return steps.length
  }
  return 1
})
</script>

<style scoped>
.skill-card {
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  position: relative;
}

.skill-card:hover {
  border-color: var(--accent2, #1f6feb);
  background: var(--bg3, #21262d);
}

.skill-card.selected {
  border-color: var(--accent2, #1f6feb);
  background: var(--accent2-dim, #1f6feb33);
}

.skill-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text, #e6edf3);
  margin-bottom: 4px;
  padding-right: 20px;
  word-break: break-word;
}

.skill-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--text3, #6e7681);
}

.skill-type {
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg3, #21262d);
  font-family: monospace;
}

.skill-type.navigate { background: #1a3d1a; color: #3fb950; }
.skill-type.click { background: #1a3a4d; color: #58a6ff; }
.skill-type.workflow_chain { background: #3b1f5e; color: #a78bfa; }

.skill-chain-hint {
  font-size: 10px;
  color: #8b5cf6;
  font-family: monospace;
}

.skill-outcome {
  font-size: 10px;
  font-family: monospace;
  padding: 1px 5px;
  border-radius: 3px;
}
.skill-outcome.success { background: #1a4d2e; color: #3fb950; }
.skill-outcome.failed { background: #4d1a1a; color: #f85149; }
.skill-outcome.in_progress { background: #1a3a4d; color: #58a6ff; }

.skill-desc {
  font-size: 10px;
  color: var(--text3, #6e7681);
  margin-bottom: 4px;
  word-break: break-word;
  line-height: 1.4;
}

.skill-delete {
  position: absolute;
  top: 6px;
  right: 8px;
  width: 18px;
  height: 18px;
  border-radius: 3px;
  border: none;
  background: transparent;
  color: var(--text3, #6e7681);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  display: none;
  align-items: center;
  justify-content: center;
}

.skill-card:hover .skill-delete { display: flex; }
.skill-delete:hover { background: #da363322; color: var(--danger, #da3633); }

.selected-indicator {
  position: absolute;
  top: 6px;
  right: 8px;
  color: var(--accent2, #1f6feb);
  font-size: 12px;
}
</style>
