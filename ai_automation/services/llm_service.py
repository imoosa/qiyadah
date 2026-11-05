"""Bounded Responses API tool loop. Only application-supplied allowlisted functions run."""
import json
import os
import requests
from ..config import Unavailable

AUTHORISED_TOOL_ALLOWLIST = frozenset({
    'capture_lead',
    'quotation_draft',
    'lookup_product_catalog',
    'check_calendar_availability',
    'book_appointment',
    'reschedule_appointment',
    'cancel_appointment',
    'request_human_takeover',
    'track_shipment',
    'search_knowledge',
    'get_business_briefing',
})

FORBIDDEN_TOOLS = frozenset({
    'execute_sql',
    'run_sql',
    'raw_query',
    'post_payment',
    'update_ledger',
    'alter_balance',
    'cancel_invoice',
    'delete_invoice',
    'post_journal_entry',
})


def validate_tool_name(name, caller_allowed=None):
    """Ensure the requested tool is in the global allowlist and caller's toolset."""
    if not name or name in FORBIDDEN_TOOLS or name not in AUTHORISED_TOOL_ALLOWLIST:
        raise PermissionError('The AI requested an operation outside its allowlist.')
    if caller_allowed is not None and name not in caller_allowed:
        raise PermissionError('The AI requested an operation outside its allowlist.')
    return name


class OpenAIProvider:
    def __init__(self, api_key, model='gpt-4o-mini', transport=None, base_url='https://api.openai.com/v1/responses'):
        if isinstance(api_key, dict):
            cfg = model if isinstance(model, dict) else {}
            model = cfg.get('model') or 'gpt-4o-mini'
            base_url = cfg.get('base_url') or base_url
            api_key = api_key.get('api_key')
        if not api_key or not model:
            raise Unavailable('Configure an API key and model before enabling AI.')
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.transport = transport or requests.Session()

    def respond(self, messages, tools, execute):
        inputs = list(messages)
        usage = {'input_tokens': 0, 'output_tokens': 0}
        for t in (tools or []):
            validate_tool_name(t.get('name'))
        allowed = {tool['name'] for tool in (tools or []) if tool.get('name') in AUTHORISED_TOOL_ALLOWLIST}
        for _ in range(3):
            try:
                payload = {
                    'model': self.model,
                    'store': False,
                    'input': inputs,
                    'parallel_tool_calls': False,
                    'max_output_tokens': 1200,
                }
                if tools:
                    payload['tools'] = tools
                response = self.transport.post(
                    self.base_url,
                    headers={'Authorization': 'Bearer ' + self.api_key},
                    json=payload,
                    timeout=(5, 35),
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError):
                raise Unavailable('The AI provider is unavailable. Please try again later.') from None
            for key in usage:
                usage[key] += int(data.get('usage', {}).get(key, 0))
            output = data.get('output', [])
            calls = [item for item in output if item.get('type') == 'function_call']
            if not calls:
                answer = '\n'.join(
                    part.get('text', '')
                    for item in output
                    if item.get('type') == 'message'
                    for part in item.get('content', [])
                    if part.get('type') == 'output_text'
                )
                if not answer and isinstance(data.get('output_text'), str):
                    answer = data['output_text']
                if not answer:
                    raise Unavailable('The provider returned no answer.')
                return answer, usage
            if len(calls) > 4:
                raise Unavailable('The provider exceeded the tool-call limit.')
            inputs.extend(output)  # Includes reasoning items required by the Responses protocol.
            for call in calls:
                validate_tool_name(call.get('name'), allowed)
                try:
                    raw_args = call.get('arguments', '{}')
                    arguments = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
                except (ValueError, KeyError, TypeError):
                    raise ValueError('Invalid AI tool arguments.') from None
                result = execute(call['name'], arguments)
                inputs.append({
                    'type': 'function_call_output',
                    'call_id': call.get('call_id', 'call_1'),
                    'output': json.dumps(result, ensure_ascii=False, default=str),
                })
        raise Unavailable('The AI reached its tool-call limit. Please narrow your question.')


class SelfHostedProvider(OpenAIProvider):
    """Configurable self-hosted OpenAI-compatible provider for future/on-prem models."""
    def __init__(self, api_key, model='qiyadah-local', base_url=None, transport=None):
        if isinstance(api_key, dict):
            cfg = model if isinstance(model, dict) else {}
            base_url = base_url or cfg.get('base_url')
            model = cfg.get('model') or 'qiyadah-local'
            api_key = api_key.get('api_key')
        resolved_url = base_url or os.environ.get('AI_SELF_HOSTED_URL') or 'http://127.0.0.1:8000/v1/responses'
        super().__init__(api_key or 'local-key', model or 'qiyadah-local', transport=transport, base_url=resolved_url)


def provider(kind, secrets=None, config=None):
    secrets = secrets or {}
    config = config or {}
    kind = (kind or 'openai').lower().strip()
    api_key = secrets.get('api_key') or os.environ.get('OPENAI_API_KEY')
    model = config.get('model') or os.environ.get('OPENAI_MODEL') or 'gpt-4o-mini'
    if kind == 'openai':
        return OpenAIProvider(api_key, model, base_url=config.get('base_url') or 'https://api.openai.com/v1/responses')
    if kind in ('self_hosted', 'local'):
        return SelfHostedProvider(api_key, model, base_url=config.get('base_url'))
    raise Unavailable('This AI provider is not installed.')
