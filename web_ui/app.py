"""
FastAPI-based Web UI for Browser-Use agent.
Migrated from Flask for async performance and modern API design.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()

from browser_use import Agent, Browser, Tools, ActionResult
from browser_use.agent.views import ActionResult

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(title='Browser-Use Web UI', version='2.0.0')

DIST_DIR = Path(__file__).parent / 'dist'
app.mount('/assets', StaticFiles(directory=str(DIST_DIR / 'assets'), html=False), name='assets')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# ============================================================================
# LLM Config Models & Storage
# ============================================================================

# Supported LLM providers with their dataclass-like config
LLM_PROVIDERS = {
	'deepseek': 'ChatDeepSeek',
	'openai': 'ChatOpenAI',
	'anthropic': 'ChatAnthropic',
	'google': 'ChatGoogle',
	'groq': 'ChatGroq',
	'mistral': 'ChatMistral',
	'ollama': 'ChatOllama',
	'cerebras': 'ChatCerebras',
	'openrouter': 'ChatOpenRouter',
	'browser-use': 'ChatBrowserUse',
}


class LLMConfig(BaseModel):
	"""LLM configuration for the agent."""
	provider: str = Field(..., description='Provider name: deepseek, openai, anthropic, google, groq, mistral, ollama, cerebras, openrouter, browser-use')
	model: str | None = Field(None, description='Model name (provider-specific)')
	api_key: str | None = Field(None, description='API key')
	base_url: str | None = Field(None, description='Custom base URL (for proxies/self-hosted)')
	temperature: float | None = Field(None, ge=0, le=2, description='Sampling temperature')
	max_tokens: int | None = Field(None, ge=1, description='Max output tokens')
	top_p: float | None = Field(None, ge=0, le=1, description='Top-p sampling')
	timeout: float | None = Field(None, ge=1, description='Request timeout in seconds')
	extra: dict[str, Any] = Field(default_factory=dict, description='Additional provider-specific params')

	model_config = ConfigDict(extra='forbid', validate_by_name=True)


class LLMConfigStore:
	"""Persisted LLM configuration store."""

	CONFIG_FILE = Path(__file__).parent / 'llm_config.json'

	def __init__(self) -> None:
		self._config: LLMConfig | None = None
		self._load()

	def _load(self) -> None:
		if self.CONFIG_FILE.exists():
			try:
				data = json.loads(self.CONFIG_FILE.read_text(encoding='utf-8'))
				self._config = LLMConfig(**data)
				logger.info('Loaded LLM config: %s', self._config.provider)
			except Exception as e:
				logger.warning('Failed to load LLM config: %s', e)

	def get(self) -> LLMConfig | None:
		return self._config

	def set(self, config: LLMConfig) -> None:
		self._config = config
		self.CONFIG_FILE.write_text(
			json.dumps(config.model_dump(), ensure_ascii=False, indent=2),
			encoding='utf-8',
		)
		logger.info('Saved LLM config: %s', config.provider)


llm_config_store = LLMConfigStore()


# ============================================================================
# Global State
# ============================================================================

sessions: dict[str, dict] = {}
skills: dict[str, dict] = {}
event_queues: dict[str, queue.Queue] = {}
step_data_store: dict[tuple[str, int], dict] = {}
human_taught_clicks: dict[str, dict] = {}
session_history: list[dict] = []  # completed sessions for history view

SKILLS_DIR = Path(__file__).parent / 'skills'
SKILLS_DIR.mkdir(exist_ok=True)

HISTORY_DIR = Path(__file__).parent / 'history'
HISTORY_DIR.mkdir(exist_ok=True)

LEARNED_ACTIONS_FILE = Path(__file__).parent / 'learned_actions.json'


def _load_history() -> list[dict]:
	loaded = []
	if HISTORY_DIR.exists():
		for f in sorted(HISTORY_DIR.glob('*.json'), key=lambda x: x.name, reverse=True)[:50]:
			try:
				loaded.append(json.loads(f.read_text(encoding='utf-8')))
			except Exception:
				pass
	return loaded


session_history = _load_history()


def _save_session_to_history(session_id: str, task: str, steps: list, success: bool, final_result: str, final_url: str):
	"""Save completed session to history directory."""
	history_entry: dict[str, Any] = {
		'session_id': session_id,
		'task': task,
		'created': datetime.now().isoformat(),
		'success': success,
		'final_result': final_result,
		'final_url': final_url,
		'steps': [],
	}
	for step_key, step_data in list(step_data_store.items()):
		if step_key[0] == session_id:
			history_entry['steps'].append(step_data)
	history_entry['steps'].sort(key=lambda s: s.get('step', 0))
	history_file = HISTORY_DIR / f'{session_id}.json'
	history_file.write_text(json.dumps(history_entry, ensure_ascii=False, indent=2), encoding='utf-8')
	session_history.insert(0, history_entry)
	if len(session_history) > 50:
		session_history.pop()



def _load_learned_actions() -> dict:
	if LEARNED_ACTIONS_FILE.exists():
		try:
			return json.loads(LEARNED_ACTIONS_FILE.read_text(encoding='utf-8'))
		except Exception:
			pass
	return {}


def _save_learned_actions(data: dict) -> None:
	LEARNED_ACTIONS_FILE.write_text(
		json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
	)


learned_actions: dict[str, dict] = _load_learned_actions()

# Load existing skills from disk
for f in SKILLS_DIR.glob('*.json'):
	try:
		data = json.loads(f.read_text(encoding='utf-8'))
		sid = data.get('id', f.stem)
		skills[sid] = data
	except Exception:
		pass


# ============================================================================
# LLM Factory
# ============================================================================

def _build_llm(config: LLMConfig):
	"""Build an LLM instance from config."""
	import httpx

	provider = config.provider
	kw: dict[str, Any] = {}
	if config.model:
		kw['model'] = config.model
	if config.api_key:
		kw['api_key'] = config.api_key
	if config.base_url:
		kw['base_url'] = config.base_url
	if config.temperature is not None:
		kw['temperature'] = config.temperature
	if config.timeout is not None:
		kw['timeout'] = config.timeout
	kw.update(config.extra)

	if provider == 'deepseek':
		from browser_use.llm.deepseek.chat import ChatDeepSeek
		return ChatDeepSeek(**kw)
	elif provider == 'openai':
		from browser_use.llm.openai.chat import ChatOpenAI
		return ChatOpenAI(**kw)
	elif provider == 'anthropic':
		from browser_use.llm.anthropic.chat import ChatAnthropic
		if config.max_tokens:
			kw.setdefault('max_tokens', config.max_tokens)
		return ChatAnthropic(**kw)
	elif provider == 'google':
		from browser_use.llm.google.chat import ChatGoogle
		if config.max_tokens:
			kw.setdefault('max_output_tokens', config.max_tokens)
		return ChatGoogle(**kw)
	elif provider == 'groq':
		from browser_use.llm.groq.chat import ChatGroq
		return ChatGroq(**kw)
	elif provider == 'mistral':
		from browser_use.llm.mistral.chat import ChatMistral
		if config.max_tokens:
			kw.setdefault('max_tokens', config.max_tokens)
		return ChatMistral(**kw)
	elif provider == 'ollama':
		from browser_use.llm.ollama.chat import ChatOllama
		if not config.model:
			kw['model'] = 'llama3'
		return ChatOllama(**kw)
	elif provider == 'cerebras':
		from browser_use.llm.cerebras.chat import ChatCerebras
		if config.max_tokens:
			kw.setdefault('max_tokens', config.max_tokens)
		return ChatCerebras(**kw)
	elif provider == 'openrouter':
		from browser_use.llm.openrouter.chat import ChatOpenRouter
		return ChatOpenRouter(**kw)
	elif provider == 'browser-use':
		from browser_use.llm.browser_use.chat import ChatBrowserUse
		return ChatBrowserUse(**kw)
	else:
		raise ValueError(f'Unknown LLM provider: {provider}')


# ============================================================================
# SSE Stream
# ============================================================================

async def sse_generator(session_id: str):
	"""Async SSE generator using event queue."""
	q = event_queues.get(session_id)
	if q is None:
		return

	while True:
		try:
			msg = q.get(timeout=1)
			if msg is None:
				break
			event_type, data = msg
			payload = json.dumps(data, ensure_ascii=False)
			yield f'event: {event_type}\ndata: {payload}\n\n'
		except queue.Empty:
			yield f'event: heartbeat\ndata: {json.dumps({"ts": datetime.now().isoformat()})}\n\n'


# ============================================================================
# LLM Trace Builder (LangSmith-like)
# ============================================================================

def _extract_text_content(content: Any) -> str:
	"""Extract plain text from various message content formats."""
	if content is None:
		return ''
	if isinstance(content, str):
		return content
	if isinstance(content, list):
		parts = []
		for item in content:
			if isinstance(item, dict):
				if item.get('type') == 'text':
					parts.append(item.get('text', ''))
				elif item.get('type') == 'image_url':
					parts.append('[image]')
			elif hasattr(item, 'text'):
				parts.append(str(item.text))
			elif hasattr(item, 'model_dump'):
				d = item.model_dump()
				if d.get('type') == 'text':
					parts.append(d.get('text', ''))
		return '\n'.join(parts)
	if hasattr(content, 'text'):
		return str(content.text)
	return str(content)


def _message_to_dict(msg: Any) -> dict[str, Any]:
	"""Convert any BaseMessage-like object to a clean dict for frontend display."""
	role = getattr(msg, 'role', 'unknown') or 'unknown'
	raw_content = getattr(msg, 'content', '') or ''

	# Extract text content
	if isinstance(raw_content, str):
		text = raw_content
		images = []
	elif isinstance(raw_content, list):
		text_parts = []
		images = []
		for part in raw_content:
			if isinstance(part, dict):
				ptype = part.get('type', '')
				if ptype == 'text':
					text_parts.append(part.get('text', ''))
				elif ptype == 'image_url':
					images.append(part.get('image_url', {}).get('url', '[image]')[:50])
			elif hasattr(part, 'type'):
				if getattr(part, 'type', None) == 'text':
					text_parts.append(getattr(part, 'text', ''))
				elif getattr(part, 'type', None) == 'image_url':
					url = getattr(part, 'image_url', {})
					if isinstance(url, dict):
						images.append(url.get('url', '[image]')[:50])
					else:
						images.append(str(url)[:50])
		text = '\n'.join(text_parts)
	else:
		text = str(raw_content)
		images = []

	# Truncate very long content for display
	if len(text) > 4000:
		text = text[:4000] + f'\n... [truncated, {len(text) - 4000} chars omitted]'

	result: dict[str, Any] = {
		'role': role,
		'text': text,
		'images': images if images else None,
	}

	# Include tool_calls if present
	if hasattr(msg, 'tool_calls') and msg.tool_calls:
		result['tool_calls'] = [
			{
				'id': tc.get('id', '') if isinstance(tc, dict) else getattr(tc, 'id', ''),
				'name': tc.get('function', {}).get('name', '') if isinstance(tc, dict) else getattr(tc, 'function', type('F', (), {'name': ''}))().name,
				'args': tc.get('function', {}).get('arguments', '') if isinstance(tc, dict) else '',
			}
			for tc in msg.tool_calls
		]

	return result


def _build_llm_trace(input_messages: list, model_output: Any, raw_response: Any) -> dict[str, Any]:
	"""
	Build a LangSmith-style LLM trace dict from input_messages + model_output + raw_response.
	"""
	trace: dict[str, Any] = {
		'timestamp': datetime.now().isoformat(),
		'model': getattr(raw_response, 'model', None) if raw_response else None,
		'stop_reason': getattr(raw_response, 'stop_reason', None) if raw_response else None,
		'usage': None,
		'input': [],
		'output': {
			'thinking': model_output.thinking or '',
			'evaluation': model_output.evaluation_previous_goal or '',
			'memory': model_output.memory or '',
			'next_goal': model_output.next_goal or '',
			'actions': [],
		},
	}

	# Token usage
	if raw_response and hasattr(raw_response, 'usage') and raw_response.usage:
		u = raw_response.usage
		trace['usage'] = {
			'prompt_tokens': getattr(u, 'prompt_tokens', 0) or 0,
			'completion_tokens': getattr(u, 'completion_tokens', 0) or 0,
			'total_tokens': getattr(u, 'total_tokens', 0) or 0,
		}

	# Serialize input messages
	trace['input'] = [_message_to_dict(msg) for msg in input_messages]

	# Serialize output actions
	for act in (model_output.action or []):
		act_data = act.model_dump(exclude_unset=True)
		trace['output']['actions'].append(act_data)

	return trace


# ============================================================================
# Agent Callbacks
# ============================================================================

def make_step_callback(session_id: str):
	def on_step(browser_state_summary, model_output, step, input_messages=None, raw_response=None):
		q = event_queues.get(session_id)
		if q is None:
			return

		selector_map = {}
		if browser_state_summary and browser_state_summary.dom_state:
			for idx, el in browser_state_summary.dom_state.selector_map.items():
				selector_map[idx] = el

		step_data: dict[str, Any] = {
			'step': step,
			'timestamp': datetime.now().isoformat(),
		}
		step_data['thinking'] = model_output.thinking or ''
		step_data['evaluation'] = model_output.evaluation_previous_goal or ''
		step_data['memory'] = model_output.memory or ''
		step_data['next_goal'] = model_output.next_goal or ''

		actions = []
		for act in (model_output.action or []):
			act_data = act.model_dump(exclude_unset=True)
			act_name = next(iter(act_data), '')
			params = act_data.get(act_name, {})
			if act_name == 'click' and params.get('index'):
				idx = params['index']
				el = selector_map.get(idx)
				if el:
					params['label'] = _get_element_label(el)
			actions.append(act_data)

		step_data['actions'] = actions
		step_data['action_labels'] = [next(iter(a.keys()), 'unknown') for a in actions]
		step_data_store[(session_id, step)] = step_data

		if browser_state_summary:
			step_data['url'] = browser_state_summary.url or ''
			step_data['title'] = browser_state_summary.title or ''

		# LLM Input/Output trace (LangSmith-like)
		if input_messages is not None:
			llm_trace = _build_llm_trace(input_messages, model_output, raw_response)
			q.put(('llm_trace', llm_trace))

		q.put(('step', step_data))

	return on_step


def _get_element_label(el: Any) -> str:
	ax_node = getattr(el, 'ax_node', None)
	if ax_node:
		name = getattr(ax_node, 'name', None)
		if name and isinstance(name, str) and name.strip():
			return name.strip()
		role = getattr(ax_node, 'role', None)
		if role and isinstance(role, str) and role.strip():
			return role.strip()

	attrs = getattr(el, 'attributes', {}) or {}
	if isinstance(attrs, dict):
		for key in ('aria-label', 'aria-labelledby', 'title', 'placeholder', 'data-testid', 'id', 'name', 'data-tooltip'):
			val = attrs.get(key)
			if val and isinstance(val, str) and val.strip():
				return val.strip()

	if isinstance(attrs, dict):
		input_type = attrs.get('type', '')
		if input_type in ('submit', 'image', 'button'):
			val = attrs.get('value', '')
			if val and isinstance(val, str) and val.strip():
				return val.strip()

	node_name = getattr(el, 'node_name', None)
	if node_name and isinstance(node_name, str):
		node_value = getattr(el, 'node_value', None)
		if node_value and isinstance(node_value, str) and node_value.strip():
			return f'[{node_name}] {node_value.strip()}'
		return node_name

	return ''


def make_done_callback(session_id: str):
	def on_done(history):
		q = event_queues.get(session_id)
		if q is None:
			return

		# Save session to history
		session_info = sessions.get(session_id, {})
		task = session_info.get('task', '')
		success = history.is_successful()
		final_result = history.final_result() or ''
		final_url = history.urls()[-1] if history.urls() else ''
		_save_session_to_history(
			session_id, task,
			list(history.history),
			success, final_result, final_url,
		)

		new_skills = extract_skills_from_history(history, session_id)
		for skill in new_skills:
			sid = skill['id']
			skills[sid] = skill
			(SKILLS_DIR / f'{sid}.json').write_text(
				json.dumps(skill, ensure_ascii=False, indent=2), encoding='utf-8'
			)

		q.put(('done', {
			'timestamp': datetime.now().isoformat(),
			'success': success,
			'final_url': final_url,
			'final_result': final_result,
			'steps_taken': history.number_of_steps(),
			'new_skills': new_skills,
		}))

	return on_done


def _normalize_url(url: str) -> str:
	"""Strip query/fragment for grouping comparison."""
	if not url:
		return ''
	from urllib.parse import urlparse
	try:
		p = urlparse(url)
		return f'{p.scheme}://{p.netloc}{p.path}'
	except Exception:
		return url


def _is_meaningful_action(act_data: dict) -> bool:
	"""Return True if this action is worth including in a skill workflow."""
	if not act_data:
		return False
	name = next(iter(act_data), '')
	return name in ('navigate', 'click', 'input', 'send_keys', 'select_dropdown', 'scroll', 'extract', 'done', 'go_back', 'switch', 'wait')


def extract_skills_from_history(history, session_id: str) -> list[dict]:
	"""
	Extract complete workflow chains as skills.

	Workflows are grouped by URL transitions:
	  - A workflow starts when the URL changes (navigate, or click leading to new URL)
	  - A workflow contains ALL actions taken between that URL and the next URL change
	  - A workflow ends when: URL changes again, agent reaches 'done', or step has error

	Each workflow becomes one Skill with:
	  - name: Human-readable summary of the workflow
	  - description: Full chain of actions with labels
	  - steps: Ordered list of {action, url, result} for replay
	"""
	new_skills = []

	# Build the full step list from history
	history_items = list(history.history)
	step_count = len(history_items)

	# Enrich with step_data_store (contains action labels, URL, etc.)
	step_info: list[dict[str, Any]] = []
	for i, item in enumerate(history_items):
		enriched = step_data_store.get((session_id, i), {})
		step_info.append({
			'index': i,
			'url': enriched.get('url', '') or (item.state.url if item.state else ''),
			'title': enriched.get('title', '') or (item.state.title if item.state else ''),
			'actions': enriched.get('actions', []),
			'thinking': enriched.get('thinking', ''),
			'evaluation': enriched.get('evaluation', ''),
			'result': item.result,
			'model_output': item.model_output,
		})

	if not step_info:
		return []

	# Detect workflow boundaries: a new workflow starts when URL changes significantly
	# or when the previous workflow ended with 'done' or a failure
	workflows: list[list[dict]] = [[]]
	current_workflow = workflows[-1]

	for i, step in enumerate(step_info):
		# Check if this step's URL differs from the last step's URL
		last_url = current_workflow[-1]['url'] if current_workflow else ''
		curr_url = step['url']
		url_changed = _normalize_url(curr_url) != _normalize_url(last_url)

		# Check if the step succeeded in reaching a goal
		eval_text = (step.get('evaluation') or '').lower()
		step_success = 'success' in eval_text or 'completed' in eval_text
		step_failed = 'fail' in eval_text or 'error' in eval_text

		# A step that has a meaningful action starts a new workflow if URL changed
		has_meaningful = any(_is_meaningful_action(a) for a in step['actions'])

		if has_meaningful and (url_changed or not current_workflow):
			# Start a new workflow if URL changed or we have no current workflow
			if current_workflow:
				workflows.append([])
				current_workflow = workflows[-1]

		current_workflow.append(step)

		# End current workflow if: done action succeeded, or step failed, or we reached the end
		if i == step_count - 1:
			continue  # don't cut early; let the last workflow include everything

	# Build skills from workflows that have at least 1 meaningful action
	skill_base_id = f'{session_id[:8]}_{len(skills)}'

	for wf_idx, workflow in enumerate(workflows):
		if not workflow:
			continue

		# Check for meaningful actions in this workflow
		meaningful = [s for s in workflow if any(_is_meaningful_action(a) for a in s['actions'])]
		if not meaningful:
			continue

		# Build action chain description
		action_chain: list[str] = []
		action_steps: list[dict[str, Any]] = []
		for step in workflow:
			for act in step['actions']:
				act_name = next(iter(act), '')
				if not _is_meaningful_action(act):
					continue
				params = act.get(act_name, {})
				if act_name == 'navigate':
					act_str = f"navigate({params.get('url', '')!r})"
				elif act_name == 'click':
					idx = params.get('index')
					label = params.get('label', '')
					act_str = f"click({label or f'#{idx}'})"
				elif act_name == 'input':
					act_str = f"input({params.get('text', '')[:30]!r})"
				elif act_name == 'done':
					act_str = "done()"
				elif act_name == 'extract':
					act_str = f"extract({params.get('goal', '')[:30]!r})"
				else:
					act_str = f"{act_name}({params})"
				action_chain.append(act_str)
				action_steps.append({
					'action': act,
					'url': step['url'],
					'title': step['title'],
				})

		if not action_chain:
			continue

		# Determine workflow outcome
		last_eval = (workflow[-1].get('evaluation') or '').lower()
		outcome = 'success' if 'success' in last_eval or 'completed' in last_eval else \
			'failed' if 'fail' in last_eval or 'error' in last_eval else 'in_progress'

		# Build name and description
		start_url = _normalize_url(workflow[0]['url'])
		end_url = _normalize_url(workflow[-1]['url'])

		if start_url and start_url != end_url:
			# Extract domain for readable name
			from urllib.parse import urlparse as _urlparse
			try:
				domain = _urlparse(start_url).netloc.replace('www.', '')
			except Exception:
				domain = start_url[:30]
			chain_summary = ' -> '.join(action_chain[:5])
			if len(action_chain) > 5:
				chain_summary += f' (+{len(action_chain) - 5} more)'
			name = f'{domain}: {workflow[0]["title"][:40] if workflow[0]["title"] else "workflow"}'
		else:
			chain_summary = ' -> '.join(action_chain[:4])
			name = chain_summary[:60]

		description = f'Workflow on {start_url or "(start)"}:\n  ' + '\n  '.join(action_chain)

		skill: dict[str, Any] = {
			'id': f'{skill_base_id}_wf{wf_idx}',
			'name': name,
			'description': description,
			'action_type': 'workflow_chain',
			'params': {
				'steps': action_steps,
				'outcome': outcome,
				'start_url': workflow[0]['url'],
				'end_url': workflow[-1]['url'],
				'step_indices': [s['index'] for s in workflow],
			},
			'context': {
				'url': workflow[0]['url'],
				'title': workflow[0]['title'],
			},
			'created_at': datetime.now().isoformat(),
			'session_id': session_id,
			'step_index': workflow[0]['index'],
		}
		new_skills.append(skill)

	# Clean up step_data_store for this session
	for key in list(step_data_store.keys()):
		if key[0] == session_id:
			del step_data_store[key]

	return new_skills


def skill_to_markdown(skill: dict[str, Any]) -> str:
	"""
	Convert a skill dict to a SKILL.md formatted string.
	Follows the format from .cursor/skills/ciq-download/SKILL.md.
	"""
	skill_id = skill.get('id', 'unknown')
	skill_name = skill.get('name', 'Untitled Skill')
	skill_desc = skill.get('description', '')
	params = skill.get('params', {})
	action_type = skill.get('action_type', 'workflow_chain')
	created_at = skill.get('created_at', '')
	context = skill.get('context', {})

	lines: list[str] = [
		'---',
		f'name: {skill_id}',
		f'description: {skill_desc.strip()}',
		'---',
		'',
		f'# {skill_name}',
		'',
	]

	if action_type == 'workflow_chain':
		start_url = params.get('start_url', '')
		end_url = params.get('end_url', '')
		steps = params.get('steps', [])
		outcome = params.get('outcome', 'unknown')

		if start_url:
			lines.append('## Overview')
			lines.append('')
			lines.append(f'**Start URL:** {start_url}')
			if end_url and end_url != start_url:
				lines.append(f'**End URL:** {end_url}')
			lines.append(f'**Outcome:** {outcome}')
			lines.append('')

		if steps:
			lines.append('## Task Steps')
			lines.append('')
			lines.append('```')
			lines.append(f'# Task: {skill_desc}')
			lines.append('')
			for i, step in enumerate(steps):
				act = step.get('action', {})
				act_name = next(iter(act), '') if act else ''
				act_params = act.get(act_name, {}) if act_name else {}
				if act_name == 'navigate':
					lines.append(f'{i + 1}. Navigate to {act_params.get("url", "")}')
				elif act_name == 'click':
					label = act_params.get('label', '')
					idx = act_params.get('index')
					desc = label or (f'element #{idx}' if idx is not None else 'element')
					lines.append(f'{i + 1}. Click: {desc}')
				elif act_name == 'input':
					lines.append(f'{i + 1}. Input: {act_params.get("text", "")[:50]}')
				elif act_name == 'extract':
					lines.append(f'{i + 1}. Extract: {act_params.get("goal", "")[:60]}')
				elif act_name == 'send_keys':
					lines.append(f'{i + 1}. Send keys: {act_params.get("keys", "")}')
				elif act_name == 'scroll':
					lines.append(f'{i + 1}. Scroll: {act_params.get("direction", "down")}')
				elif act_name == 'done':
					lines.append(f'{i + 1}. Mark task as done')
				elif act_name == 'select_dropdown':
					lines.append(f'{i + 1}. Select dropdown: {act_params.get("value", "")}')
				elif act_name == 'go_back':
					lines.append(f'{i + 1}. Go back')
				elif act_name == 'switch':
					lines.append(f'{i + 1}. Switch tab')
				elif act_name == 'wait':
					lines.append(f'{i + 1}. Wait {act_params.get("seconds", "")}s')
				elif act_name == 'search':
					lines.append(f'{i + 1}. Search: {act_params.get("query", "")}')
				elif act_name:
					lines.append(f'{i + 1}. {act_name}')
			lines.append('```')
			lines.append('')

		if context:
			lines.append('## Context')
			lines.append('')
			if context.get('title'):
				lines.append(f'- **Page Title:** {context["title"]}')
			if context.get('url'):
				lines.append(f'- **URL:** {context["url"]}')
			lines.append('')

		lines.append('## Notes')
		lines.append('')
		lines.append('- This skill was auto-generated from a completed task workflow.')
		lines.append(f'- Created: {created_at}')
		lines.append(f'- Session: {skill.get("session_id", "unknown")}')

	else:
		lines.append('## Overview')
		lines.append('')
		lines.append(skill_desc)
		lines.append('')
		lines.append('## Parameters')
		lines.append('')
		for key, val in params.items():
			lines.append(f'- `{key}`: {val}')
		lines.append('')
		lines.append('## Notes')
		lines.append('')
		lines.append(f'- Created: {created_at}')

	return '\n'.join(lines)




def _build_tools_with_human_help(session_id: str):
	tools = Tools()

	@tools.action(
		description=(
			'Request human help. Use ONLY when you are stuck — e.g., a button cannot be '
			'found or clicked after multiple retries. Describe what you need the human to do '
			'and wait for their response.'
		),
	)
	async def request_human_help(question: str) -> ActionResult:
		q = event_queues.get(session_id)
		if q is None:
			return ActionResult(extracted_content='Session not found')

		q.put(('human_help', {
			'session_id': session_id,
			'question': question,
			'url': '',
			'timestamp': datetime.now().isoformat(),
		}))

		human_taught_clicks[session_id] = {
			'status': 'waiting',
			'url': '',
			'question': question,
		}

		return ActionResult(
			extracted_content=(
				'Waiting for human help. The human has been notified and will assist you. '
				'Do NOT retry the same action. Wait for the human_help_result event.'
			),
		)

	return tools


def _build_learned_actions_context() -> str:
	if not learned_actions:
		return ''

	lines = [
		'',
		'## Previously Learned Actions (Human-Taught)',
		'You have learned the following actions from past human help. Use these when you encounter the same situation:',
		'',
	]
	for key, info in learned_actions.items():
		url_pattern = info.get('url_pattern', '')
		button_text = info.get('button_text', '')
		target_url = info.get('target_url', '')
		hint = info.get('hint', '')
		lines.append(f'- On **{url_pattern}**, click *"{button_text}"* -> goes to {target_url}')
		if hint:
			lines.append(f'  Hint: {hint}')

	return '\n'.join(lines)


# ============================================================================
# Routes
# ============================================================================

@app.get('/')
async def index():
	"""Serve the Vue SPA entry point."""
	return Response(
		content=Path(__file__).parent.joinpath('templates', 'index.html').read_text(encoding='utf-8'),
		media_type='text/html',
	)


@app.get('/api/providers')
async def list_providers():
	"""List all supported LLM providers and their default models."""
	from browser_use.llm.deepseek.chat import ChatDeepSeek
	from browser_use.llm.openai.chat import ChatOpenAI
	from browser_use.llm.anthropic.chat import ChatAnthropic
	from browser_use.llm.google.chat import ChatGoogle
	from browser_use.llm.groq.chat import ChatGroq
	from browser_use.llm.mistral.chat import ChatMistral
	from browser_use.llm.ollama.chat import ChatOllama
	from browser_use.llm.cerebras.chat import ChatCerebras
	from browser_use.llm.openrouter.chat import ChatOpenRouter
	from browser_use.llm.browser_use.chat import ChatBrowserUse

	return JSONResponse({
		'providers': [
			{
				'id': 'browser-use',
				'name': 'Browser Use Cloud',
				'description': 'Best performance, built for browser automation',
				'class': 'ChatBrowserUse',
				'default_model': 'bu-latest',
				'fields': ['api_key', 'model', 'base_url', 'timeout'],
			},
			{
				'id': 'deepseek',
				'name': 'DeepSeek',
				'description': 'Cost-effective reasoning models',
				'class': 'ChatDeepSeek',
				'default_model': 'deepseek-chat',
				'fields': ['api_key', 'base_url', 'model', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'openai',
				'name': 'OpenAI',
				'description': 'GPT-4o, o1, o3 family models',
				'class': 'ChatOpenAI',
				'default_model': 'gpt-4o',
				'fields': ['api_key', 'model', 'base_url', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'anthropic',
				'name': 'Anthropic',
				'description': 'Claude 3.5 Sonnet, Haiku models',
				'class': 'ChatAnthropic',
				'default_model': 'claude-sonnet-4-20250514',
				'fields': ['api_key', 'model', 'base_url', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'google',
				'name': 'Google Gemini',
				'description': 'Gemini 2.0 Flash, Pro models',
				'class': 'ChatGoogle',
				'default_model': 'gemini-2.0-flash',
				'fields': ['api_key', 'model', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'groq',
				'name': 'Groq',
				'description': 'Fast inference with Llama, Mixtral',
				'class': 'ChatGroq',
				'default_model': 'llama-3.3-70b-versatile',
				'fields': ['api_key', 'model', 'temperature', 'top_p', 'timeout'],
			},
			{
				'id': 'mistral',
				'name': 'Mistral',
				'description': 'Mistral Large, Small models',
				'class': 'ChatMistral',
				'default_model': 'mistral-large-latest',
				'fields': ['api_key', 'model', 'base_url', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'ollama',
				'name': 'Ollama',
				'description': 'Local models via Ollama',
				'class': 'ChatOllama',
				'default_model': 'llama3',
				'fields': ['model', 'host'],
			},
			{
				'id': 'cerebras',
				'name': 'Cerebras',
				'description': 'Ultra-fast Llama inference',
				'class': 'ChatCerebras',
				'default_model': 'llama3.3-70b',
				'fields': ['api_key', 'model', 'base_url', 'temperature', 'top_p', 'max_tokens', 'timeout'],
			},
			{
				'id': 'openrouter',
				'name': 'OpenRouter',
				'description': 'Access 200+ models via OpenRouter',
				'class': 'ChatOpenRouter',
				'default_model': 'anthropic/claude-3.5-sonnet',
				'fields': ['api_key', 'model', 'base_url', 'temperature', 'top_p', 'timeout'],
			},
		]
	})


# ============================================================================
# LLM Config Routes
# ============================================================================

@app.get('/api/config/llm')
async def get_llm_config():
	"""Get current LLM configuration (secrets masked)."""
	cfg = llm_config_store.get()
	if cfg is None:
		return JSONResponse({'config': None})
	# Return a safe copy with api_key masked
	unsafe_copy = cfg.model_dump()
	if unsafe_copy.get('api_key'):
		unsafe_copy['api_key'] = mask_secret(unsafe_copy['api_key'])
	return JSONResponse({'config': unsafe_copy})


@app.put('/api/config/llm')
async def update_llm_config(config: LLMConfig):
	"""Update LLM configuration."""
	# Validate the config by attempting to build the LLM
	try:
		_build_llm(config)
	except Exception as e:
		raise HTTPException(status_code=400, detail=f'Invalid config: {e}')
	llm_config_store.set(config)
	cfg = config.model_dump()
	if cfg.get('api_key'):
		cfg['api_key'] = mask_secret(cfg['api_key'])
	return JSONResponse({'config': cfg})


def mask_secret(key: str) -> str:
	if not key or len(key) < 8:
		return '***'
	return key[:4] + '***' + key[-4:]


# ============================================================================
# Session Routes
# ============================================================================

@app.post('/api/sessions')
async def create_session():
	session_id = uuid.uuid4().hex[:12]
	q: queue.Queue[Any] = queue.Queue()
	event_queues[session_id] = q
	sessions[session_id] = {
		'status': 'idle',
		'task': '',
		'created': datetime.now().isoformat(),
	}
	return JSONResponse({'session_id': session_id})


@app.post('/api/sessions/{session_id}/execute')
async def execute_task(session_id: str, body: dict[str, Any] | None = None):
	if session_id not in sessions:
		raise HTTPException(status_code=404, detail='Session not found')

	task = (body or {}).get('task', '').strip()
	if not task:
		raise HTTPException(status_code=400, detail='Task is required')

	sessions[session_id]['status'] = 'running'
	sessions[session_id]['task'] = task

	q = event_queues[session_id]
	q.put(('status', {'status': 'running', 'task': task}))

	def run_agent():
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		try:
			loop.run_until_complete(_run_agent_async(session_id, task))
		except Exception as e:
			q.put(('error', {'message': str(e)}))
		finally:
			sessions[session_id]['status'] = 'done'
			q.put(('status', {'status': 'done'}))
			loop.close()

	thread = threading.Thread(target=run_agent, daemon=True)
	thread.start()

	return JSONResponse({'status': 'started'})


async def _run_agent_async(session_id: str, task: str):
	q = event_queues[session_id]

	# Use configured LLM or fall back to env-based
	cfg = llm_config_store.get()
	if cfg:
		llm = _build_llm(cfg)
		provider_name = cfg.provider
	else:
		# Fallback: try DeepSeek from env
		from browser_use.llm.deepseek.chat import ChatDeepSeek
		llm = ChatDeepSeek(
			model=os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
			api_key=os.getenv('DEEPSEEK_API_KEY'),
			base_url='https://api.deepseek.com',
		)
		provider_name = 'deepseek-chat'

	browser = Browser(
		headless=False,
		minimum_wait_page_load_time=2.0,
	)

	username = os.getenv('CAPITALIQ_USERNAME', '')
	password = os.getenv('CAPITALIQ_PASSWORD', '')
	if username and password:
		task_with_creds = (
			f'IMPORTANT: Login credentials:\n- Email: {username}\n- Password: {password}\n\nTask:\n{task}'
		)
	else:
		task_with_creds = task

	learned_context = _build_learned_actions_context()
	if learned_context:
		task_with_creds = task_with_creds + '\n\n' + learned_context

	tools = _build_tools_with_human_help(session_id)

	agent = Agent(
		task=task_with_creds,
		llm=llm,
		browser=browser,
		tools=tools,
		step_timeout=300,
		register_new_step_callback=make_step_callback(session_id),
		register_done_callback=make_done_callback(session_id),
	)

	q.put(('agent_info', {
		'session_id': session_id,
		'model': provider_name,
		'started_at': datetime.now().isoformat(),
	}))

	await agent.run()


@app.get('/api/sessions/{session_id}/status')
async def get_status(session_id: str):
	if session_id not in sessions:
		raise HTTPException(status_code=404, detail='not found')
	return JSONResponse(sessions[session_id])


@app.post('/api/sessions/{session_id}/stop')
async def stop_session(session_id: str):
	if session_id not in sessions:
		raise HTTPException(status_code=404, detail='not found')
	sessions[session_id]['status'] = 'stopping'
	q = event_queues[session_id]
	q.put(('status', {'status': 'stopping'}))
	return JSONResponse({'status': 'stopping'})


@app.get('/events/{session_id}')
async def events(session_id: str):
	if session_id not in event_queues:
		raise HTTPException(status_code=404, detail='Session not found')
	return StreamingResponse(
		sse_generator(session_id),
		media_type='text/event-stream',
		headers={
			'Cache-Control': 'no-cache',
			'Connection': 'keep-alive',
			'X-Accel-Buffering': 'no',
		},
	)


# ============================================================================
# Human Help Routes
# ============================================================================

@app.get('/api/sessions/{session_id}/human-help-status')
async def human_help_status(session_id: str):
	pending = human_taught_clicks.get(session_id, {})
	return JSONResponse({
		'waiting': pending.get('status') == 'waiting',
		'url': pending.get('url', ''),
		'question': pending.get('question', ''),
	})


@app.post('/api/sessions/{session_id}/human-help')
async def submit_human_help(session_id: str, body: dict[str, Any]):
	if session_id not in sessions:
		raise HTTPException(status_code=404, detail='not found')

	button_text = body.get('button_text', '').strip()
	if not button_text:
		raise HTTPException(status_code=400, detail='button_text is required')

	element_index = body.get('element_index')
	url_on_click = body.get('url_on_click', '').strip()
	description = body.get('description', '').strip()
	question = body.get('question', '').strip()

	q = event_queues.get(session_id)
	pending = human_taught_clicks.get(session_id, {})

	key = f"{pending.get('url', '')}|{button_text}"
	learned_actions[key] = {
		'url_pattern': pending.get('url', ''),
		'button_text': button_text,
		'target_url': url_on_click,
		'description': description,
		'question': question,
		'element_index': element_index,
		'learned_at': datetime.now().isoformat(),
	}
	_save_learned_actions(learned_actions)

	if q and pending.get('status') == 'waiting':
		q.put(('human_help_result', {
			'button_text': button_text,
			'element_index': element_index,
			'url_on_click': url_on_click,
			'learned': True,
		}))

	if session_id in human_taught_clicks:
		del human_taught_clicks[session_id]

	return JSONResponse({
		'learned': True,
		'key': key,
		'total_learned': len(learned_actions),
		'message': f'Learned: on "{pending.get("url", "")}" -> click "{button_text}"',
	})


# ============================================================================
# Skills Routes
# ============================================================================

@app.get('/api/skills')
async def list_skills(session_id: str | None = None):
	skill_list = list(skills.values())
	if session_id:
		skill_list = [s for s in skill_list if s.get('session_id') == session_id]
	return JSONResponse({'skills': skill_list})


@app.put('/api/skills/{skill_id}')
async def update_skill(skill_id: str, body: dict[str, Any]):
	if skill_id not in skills:
		raise HTTPException(status_code=404, detail='not found')
	skills[skill_id].update({
		k: v for k, v in body.items()
		if k in ('name', 'description')
	})
	(SKILLS_DIR / f'{skill_id}.json').write_text(
		json.dumps(skills[skill_id], ensure_ascii=False, indent=2), encoding='utf-8'
	)
	return JSONResponse(skills[skill_id])


@app.delete('/api/skills/{skill_id}')
async def delete_skill(skill_id: str):
	if skill_id not in skills:
		raise HTTPException(status_code=404, detail='not found')
	del skills[skill_id]
	f = SKILLS_DIR / f'{skill_id}.json'
	if f.exists():
		f.unlink()
	return JSONResponse({'deleted': skill_id})


@app.post('/api/skills/compose')
async def compose_task(body: dict[str, Any]):
	skill_ids = body.get('skill_ids', [])
	if not skill_ids:
		return JSONResponse({'task': ''})

	parts = []
	for sid in skill_ids:
		if sid not in skills:
			continue
		s = skills[sid]

		if s['action_type'] == 'workflow_chain':
			# Full workflow chain — compose into a coherent task description
			params = s.get('params', {})
			steps = params.get('steps', [])
			start_url = params.get('start_url', '')
			if start_url:
				parts.append(f'1. Navigate to {start_url}')
			for j, step in enumerate(steps):
				act = step.get('action', {})
				act_name = next(iter(act), '')
				act_params = act.get(act_name, {}) if act_name else {}
				if act_name == 'navigate':
					parts.append(f'{len(parts) + 1}. Navigate to {act_params.get("url", "")}')
				elif act_name == 'click':
					label = act_params.get('label', '')
					idx = act_params.get('index')
					desc = label or f'element #{idx}' if idx is not None else 'the right element'
					parts.append(f'{len(parts) + 1}. Click {desc}')
				elif act_name == 'input':
					parts.append(f'{len(parts) + 1}. Enter text: {act_params.get("text", "")[:40]}')
				elif act_name == 'extract':
					parts.append(f'{len(parts) + 1}. Extract: {act_params.get("goal", "")[:60]}')
				elif act_name == 'done':
					parts.append(f'{len(parts) + 1}. Mark task as done')
		elif s['action_type'] == 'navigate':
			url = s['params'].get('url', '')
			parts.append(f'{len(parts) + 1}. Navigate to {url}')
		elif s['action_type'] == 'click':
			idx = s['params'].get('index', '')
			label = s['params'].get('label', '')
			desc = label or f'element #{idx}' if idx is not None else 'element'
			parts.append(f'{len(parts) + 1}. Click on the {desc}')

	task = '\n'.join(parts) if parts else ''
	return JSONResponse({'task': task})


@app.post('/api/sessions/{session_id}/save-as-skill')
async def save_session_as_skill(session_id: str, body: dict[str, Any] | None = None):
	"""Save a completed session's latest auto-generated skill as a .cursor/skills/SKILL.md file."""
	# Find the most recent skill for this session
	session_skills = [s for s in skills.values() if s.get('session_id') == session_id]
	if not session_skills:
		raise HTTPException(status_code=404, detail='No skills found for this session')

	# Use the first skill from this session (most recent one added)
	skill = session_skills[0]
	skill_name = (body or {}).get('name', skill.get('name', 'Untitled')).strip()
	if not skill_name:
		skill_name = skill.get('name', 'Untitled Skill')

	skill_id_for_path = skill_name.lower().replace(' ', '-').replace('/', '-').replace('\\', '-')
	skill_id_for_path = ''.join(c for c in skill_id_for_path if c.isalnum() or c in '-_')

	markdown = skill_to_markdown(skill)
	markdown = markdown.replace('---', f'---\nname: {skill_id_for_path}', 1)
	markdown = markdown.replace('description: ', f'description: {skill_name} - ', 1)

	skill_dir = Path(__file__).parent.parent / '.cursor' / 'skills' / skill_id_for_path
	skill_dir.mkdir(parents=True, exist_ok=True)
	skill_md_path = skill_dir / 'SKILL.md'
	skill_md_path.write_text(markdown, encoding='utf-8')

	# Also save the skill JSON for persistence
	json_path = skill_dir / 'skill.json'
	json_data = {**skill, 'name': skill_name}
	json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding='utf-8')

	# Register in the in-memory skills dict and persist
	skill['name'] = skill_name
	skill['id'] = skill_id_for_path
	skills[skill_id_for_path] = skill
	(SKILLS_DIR / f'{skill_id_for_path}.json').write_text(
		json.dumps(skill, ensure_ascii=False, indent=2), encoding='utf-8'
	)

	return JSONResponse({
		'path': str(skill_md_path),
		'markdown': markdown,
		'skill_id': skill_id_for_path,
	})


# ============================================================================
# History Routes
# ============================================================================

@app.get('/api/history')
async def list_history():
	return JSONResponse({'history': session_history})


@app.get('/api/history/{session_id}')
async def get_history_session(session_id: str):
	# First check in-memory
	for entry in session_history:
		if entry.get('session_id') == session_id:
			return JSONResponse(entry)
	# Then check disk
	hist_file = HISTORY_DIR / f'{session_id}.json'
	if hist_file.exists():
		return JSONResponse(json.loads(hist_file.read_text(encoding='utf-8')))
	raise HTTPException(status_code=404, detail='not found')


# ============================================================================
# Learned Actions Routes
# ============================================================================

@app.get('/api/learned-actions')
async def list_learned_actions():
	return JSONResponse({'learned_actions': list(learned_actions.values())})


@app.delete('/api/learned-actions/{key}')
async def delete_learned_action(key: str):
	import urllib.parse
	key_decoded = urllib.parse.unquote(key)
	if key_decoded in learned_actions:
		del learned_actions[key_decoded]
		_save_learned_actions(learned_actions)
		return JSONResponse({'deleted': key_decoded})
	raise HTTPException(status_code=404, detail='not found')


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
	print('=' * 60)
	print('  Browser-Use Web UI (FastAPI)')
	print('  Open: http://127.0.0.1:5000')
	print('=' * 60)
	uvicorn.run(app, host='0.0.0.0', port=5000)
