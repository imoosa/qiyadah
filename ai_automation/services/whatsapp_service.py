"""Company-specific WhatsApp adapters; ambiguous delivery is never retried."""
import hashlib
import hmac
import re
import requests
from ..config import Unavailable


class Retryable(Unavailable):
    """Provider explicitly rejected before accepting the message (e.g. 429)."""


class DeliveryUnknown(Unavailable):
    """Provider may have accepted this message. Operator reconciliation needed."""


def verify_signature(raw, signature, app_secret):
    expected = 'sha256=' + hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return bool(app_secret and signature and hmac.compare_digest(expected, signature))


class MetaWhatsApp:
    def __init__(self, config, secrets, transport=None):
        self.config, self.secrets = config, secrets
        self.http = transport or requests.Session()
        version = config.get('api_version', '')
        if not re.fullmatch(r'v[0-9]+\.0', version) or not str(config.get('phone_number_id', '')).isdigit():
            raise Unavailable('Configure the Meta API version and phone number ID.')
        self.base = 'https://graph.facebook.com/' + version
        self.headers = {'Authorization': 'Bearer ' + secrets.get('access_token', '')}

    def send(self, recipient, payload, template=None):
        body = {'messaging_product': 'whatsapp', 'to': recipient}
        if template:
            if template not in self.config.get('templates', []):
                raise Unavailable('This template is not enabled for the company.')
            waba = str(self.config.get('waba_id', ''))
            if not waba.isdigit():
                raise Unavailable('Configure the WhatsApp Business Account ID.')
            try:
                check = self.http.get(self.base + '/' + waba + '/message_templates',
                    params={'name': template, 'fields': 'name,status,language', 'limit': 100}, headers=self.headers, timeout=(5, 15))
                check.raise_for_status()
                approved = any(t.get('name') == template and t.get('status') == 'APPROVED'
                               and t.get('language') == self.config.get('language', 'en') for t in check.json().get('data', []))
            except (requests.RequestException, ValueError):
                raise Retryable('Template approval verification is temporarily unavailable.') from None
            if not approved:
                raise Unavailable('The provider has not approved this template and language.')
            body.update(type='template', template={'name': template, 'language': {'code': self.config.get('language', 'en')},
                'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(p)} for p in payload.get('parameters', [])]}]})
        else:
            body.update(type='text', text={'body': payload['text'][:4000]})
        try:
            response = self.http.post(self.base + '/' + str(self.config['phone_number_id']) + '/messages',
                                       json=body, headers=self.headers, timeout=(5, 20))
        except requests.RequestException:
            raise DeliveryUnknown('Delivery outcome is unknown; reconcile with the provider before retrying.') from None
        if response.status_code == 429:
            raise Retryable('Provider rate limit; retry later.')
        if response.status_code >= 500:
            raise DeliveryUnknown('Provider delivery outcome is unknown.')
        if response.status_code >= 400:
            raise Unavailable('The provider rejected the message. Check template and account settings.')
        try:
            return response.json()['messages'][0]['id']
        except (ValueError, KeyError, IndexError):
            raise DeliveryUnknown('Provider accepted the request without a delivery reference.') from None


class ExistingWhatsApp:
    def __init__(self, company, config):
        self.company, self.config = company, config

    def send(self, recipient, payload, template=None):
        if not template or template not in self.config.get('templates', []):
            raise Unavailable('Choose a company-approved template for the existing WhatsApp integration.')
        from whatsapp_service import _send_whatsapp_template
        result = _send_whatsapp_template(self.company, recipient, template, payload.get('parameters', []))
        if not result.get('success') or not result.get('message_id'):
            raise DeliveryUnknown('Existing WhatsApp adapter requires provider reconciliation.')
        return result['message_id']
