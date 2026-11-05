"""Direct Meta Cloud API review client. No credential persistence or automatic retries."""
import hashlib
import hmac
import os
import re
import json
from urllib.parse import urlsplit
import requests
from ai_automation.config import contact


class MetaError(ValueError):
    pass


def template_buttons(form):
    buttons = [dict(type='QUICK_REPLY', text=s.strip()) for s in form.get('buttons', '').split('|') if s.strip()]
    if 'buttons_json' in form:
        try:
            buttons = json.loads(form['buttons_json'])
        except (ValueError, TypeError):
            raise MetaError('Invalid button configuration.') from None
    if not isinstance(buttons, list) or len(buttons) > 10:
        raise MetaError('Use up to 10 buttons.')
    cleaned, labels, counts = [], set(), {}
    for button in buttons:
        if not isinstance(button, dict):
            raise MetaError('Invalid button configuration.')
        kind, label = button.get('type'), button.get('text')
        if kind not in ('QUICK_REPLY', 'URL', 'PHONE_NUMBER') or not isinstance(label, str) or not label.strip() or len(label.strip()) > 25 or label.strip() in labels:
            raise MetaError('Use supported button types with unique labels of 1–25 characters.')
        labels.add(label.strip())
        counts[kind] = counts.get(kind, 0) + 1
        item = {'type': kind, 'text': label.strip()}
        if kind == 'URL':
            url = button.get('url', '')
            if not isinstance(url, str) or len(url) > 2000 or any(c.isspace() for c in url) or '{' in url or '}' in url:
                raise MetaError('Enter a static website URL without variables or spaces.')
            try:
                parsed = urlsplit(url)
                valid = parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password
            except ValueError:
                valid = False
            if not valid:
                raise MetaError('Website buttons need a valid http or https URL.')
            item['url'] = url
        if kind == 'PHONE_NUMBER':
            phone = button.get('phone_number', '')
            if not isinstance(phone, str) or not re.fullmatch(r'\+[1-9][0-9]{6,14}', phone):
                raise MetaError('Enter a phone button number with + and its country code.')
            item['phone_number'] = phone
        cleaned.append(item)
    if counts.get('URL', 0) > 2 or counts.get('PHONE_NUMBER', 0) > 1:
        raise MetaError('Use at most two website buttons and one phone button.')
    cleaned.sort(key=lambda button: button['type'] != 'QUICK_REPLY')
    return cleaned


def template_payload(form):
    name, language = form.get('name', ''), form.get('language', '')
    category = form.get('category', '')
    if not re.fullmatch(r'[a-z0-9_]{1,512}', name):
        raise MetaError('Template name must use lowercase letters, digits and underscores.')
    if not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?', language):
        raise MetaError('Enter a Meta language code, such as en_US.')
    if category not in ('UTILITY', 'MARKETING'):
        raise MetaError('This text-template editor supports UTILITY and MARKETING. Authentication requires a separate schema.')
    components = []
    for kind, limit in (('header', 60), ('body', 1024), ('footer', 60)):
        value = form.get(kind, '').strip()
        if not value:
            if kind == 'body':
                raise MetaError('Template body is required.')
            continue
        if len(value) > limit:
            raise MetaError(f'{kind.title()} exceeds {limit} characters.')
        slots = re.findall(r'\{\{([1-9][0-9]*)\}\}', value)
        if '{{' in re.sub(r'\{\{[1-9][0-9]*\}\}', '', value) or '}}' in re.sub(r'\{\{[1-9][0-9]*\}\}', '', value):
            raise MetaError('Use numbered variables such as {{1}}.')
        numbers = sorted(set(map(int, slots)))
        if numbers != list(range(1, len(numbers) + 1)) or (kind == 'footer' and slots) or (kind == 'header' and len(numbers) > 1):
            raise MetaError('Variables must be sequential; header supports one and footer none.')
        item = {'type': kind.upper(), 'text': value}
        if kind == 'header':
            item['format'] = 'TEXT'
        if numbers:
            samples = ([str(form.get(f'{kind}_sample_{n}', '')).strip() for n in numbers]
                       if any(f'{kind}_sample_{n}' in form for n in numbers)
                       else [s.strip() for s in form.get(kind + '_samples', '').split('|')])
            if len(samples) != len(numbers) or not all(samples):
                raise MetaError(f'Provide one pipe-separated sample for each {kind} variable.')
            item['example'] = {kind + '_text': [samples] if kind == 'body' else samples}
        components.append(item)
    buttons = template_buttons(form)
    if buttons:
        components.append({'type': 'BUTTONS', 'buttons': buttons})
    return dict(name=name, language=language, category=category, components=components)


class MetaReviewClient:
    def __init__(self, environment=None, http=None):
        self.env = os.environ if environment is None else environment
        self.http = http or requests
        self.version = self.env.get('META_GRAPH_API_VERSION', '')
        self.waba = self.env.get('META_WABA_ID', '')
        self.phone = self.env.get('META_PHONE_NUMBER_ID', '')
        self.token = self.env.get('META_ACCESS_TOKEN', '')
        if not re.fullmatch(r'v[0-9]+\.0', self.version) or not self.waba.isdigit() or not self.phone.isdigit() or not self.token:
            raise MetaError('Configure Meta API version, WABA ID, phone number ID and server-side access token.')

    def clean(self, value):
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items() if k.lower() not in ('access_token', 'paging', 'authorization', 'appsecret_proof')}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for key in ('META_ACCESS_TOKEN', 'META_APP_SECRET', 'META_WEBHOOK_VERIFY_TOKEN', 'META_WEBHOOK_APP_SECRET'):
                secret = self.env.get(key)
                if secret:
                    value = value.replace(secret, '[redacted]')
            value = re.sub(r'(?i)Bearer\s+\S+', 'Bearer [redacted]', value)
        return value

    def call(self, method, path, payload=None, params=None):
        query = dict(params or {})
        secret = self.env.get('META_APP_SECRET')
        if secret:
            query['appsecret_proof'] = hmac.new(secret.encode(), self.token.encode(), hashlib.sha256).hexdigest()
        try:
            response = self.http.request(method, f'https://graph.facebook.com/{self.version}/{path}',
                headers={'Authorization': 'Bearer ' + self.token}, params=query, json=payload,
                timeout=(5, 20), allow_redirects=False)
        except requests.RequestException:
            raise MetaError('Network failure: outcome may be unknown. Check Meta before retrying; no automatic retry was made.') from None
        try:
            data = self.clean(response.json())
        except ValueError:
            raise MetaError('Meta returned a non-JSON response; reconcile before retrying.') from None
        if not isinstance(data, dict):
            raise MetaError('Unexpected Meta response.')
        if response.status_code >= 300 or 'error' in data:
            error = data.get('error', {})
            if not isinstance(error, dict):
                error = {}
            details = []
            extra = error.get('error_data', {})
            for value in (error.get('error_user_title'), error.get('error_user_msg'),
                          extra.get('details') if isinstance(extra, dict) else None):
                if isinstance(value, str) and value.strip() and value.strip() not in details:
                    details.append(value.strip())
            explanation = ' — '.join(details) or error.get('message', 'Request rejected')
            raise MetaError(f"Meta HTTP {response.status_code}, code {error.get('code', 'unknown')}, subcode {error.get('error_subcode', '-')}: {explanation}; trace {error.get('fbtrace_id', '-')}")
        return data

    def templates(self, name=None):
        params = {'fields': 'id,name,status,language,category,components', 'limit': 100}
        if name:
            params['name'] = name
        return self.call('GET', self.waba + '/message_templates', params=params)

    def account(self):
        return self.call('GET', self.waba, params={'fields': 'id,name'})

    def create(self, form):
        return self.call('POST', self.waba + '/message_templates', template_payload(form))

    def send(self, recipient, name, language, phone, values=None):
        recipient = contact(recipient, 'whatsapp')
        allowed = {contact(v, 'whatsapp') for v in self.env.get('META_TEST_RECIPIENTS', '').split(',') if v.strip()}
        if recipient not in allowed:
            raise MetaError('Recipient is not in the server-configured verified test-recipient allowlist.')
        if phone != self.phone:
            raise MetaError('Only the configured test sender can be used.')
        templates = self.templates(name).get('data', [])
        selected = next((t for t in templates if t.get('name') == name and t.get('language') == language and t.get('status') == 'APPROVED'), None)
        if not selected:
            raise MetaError('Meta has not approved this template and language.')
        components = []
        values = values or {}
        for component in selected.get('components', []):
            kind = component.get('type')
            if kind not in ('BODY', 'FOOTER', 'HEADER') or (kind == 'HEADER' and component.get('format') != 'TEXT'):
                raise MetaError('This test sender supports text headers and bodies. Media and buttons are not supported yet.')
            slots = list(dict.fromkeys(re.findall(r'{{\s*([a-zA-Z0-9_]+)\s*}}', component.get('text', ''))))
            if not slots:
                continue
            if all(slot.isdigit() for slot in slots):
                slots.sort(key=int)
            parameters = []
            for slot in slots:
                value = str(values.get(f'{kind.lower()}_{slot}', '')).strip()
                if not value:
                    raise MetaError(f'Enter a value for {kind.lower()} variable {slot}.')
                if len(value) > 1024:
                    raise MetaError('Template variable values must be at most 1024 characters.')
                parameter = {'type': 'text', 'text': value}
                if not slot.isdigit():
                    parameter['parameter_name'] = slot
                parameters.append(parameter)
            components.append({'type': kind.lower(), 'parameters': parameters})
        template = {'name': name, 'language': {'code': language}}
        if components:
            template['components'] = components
        return self.call('POST', self.phone + '/messages', {'messaging_product': 'whatsapp', 'to': recipient,
            'type': 'template', 'template': template})
