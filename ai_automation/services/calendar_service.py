"""Google Calendar API transport; callers hold a per-calendar booking lock."""
from urllib.parse import quote
import requests
from ..config import Unavailable


class GoogleCalendar:
    def __init__(self, config, secrets, transport=None):
        self.calendar = config.get('calendar_id', '')
        self.http = transport or requests.Session()
        try:
            response = self.http.post('https://oauth2.googleapis.com/token', data={
                'grant_type': 'refresh_token', 'client_id': secrets['client_id'],
                'client_secret': secrets['client_secret'], 'refresh_token': secrets['refresh_token']}, timeout=(5, 15))
            response.raise_for_status()
            self.headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
        except (requests.RequestException, ValueError, KeyError):
            raise Unavailable('Google Calendar authorization is unavailable. Reconnect this company calendar.') from None
        self.url = 'https://www.googleapis.com/calendar/v3/calendars/' + quote(self.calendar, safe='') + '/events'

    def available(self, start, end):
        try:
            response = self.http.post('https://www.googleapis.com/calendar/v3/freeBusy', headers=self.headers,
                json={'timeMin': start, 'timeMax': end, 'items': [{'id': self.calendar}]}, timeout=(5, 15))
            response.raise_for_status()
            result = response.json()['calendars'][self.calendar]
            if 'busy' not in result or result.get('errors'):
                raise ValueError('No reliable availability')
            return not result['busy']
        except (requests.RequestException, ValueError, KeyError):
            raise Unavailable('Calendar availability could not be verified.') from None

    def book(self, identifier, title, start, end):
        body = {'id': identifier, 'summary': title, 'start': {'dateTime': start}, 'end': {'dateTime': end}}
        try:
            response = self.http.post(self.url, json=body, headers=self.headers, timeout=(5, 15))
            if response.status_code == 409:
                response = self.http.get(self.url + '/' + identifier, headers=self.headers, timeout=(5, 15))
            response.raise_for_status()
            return response.json()['id']
        except (requests.RequestException, ValueError, KeyError):
            raise Unavailable('Booking is unconfirmed. Reconcile the stored event reference before retrying.') from None

    def cancel(self, identifier):
        try:
            response = self.http.delete(self.url + '/' + quote(identifier, safe=''), headers=self.headers, timeout=(5, 15))
            if response.status_code not in (404, 410):
                response.raise_for_status()
        except requests.RequestException:
            raise Unavailable('Calendar cancellation could not be confirmed.') from None

    def reschedule(self, identifier, start, end):
        try:
            response = self.http.patch(self.url + '/' + quote(identifier, safe=''), headers=self.headers,
                json={'start': {'dateTime': start}, 'end': {'dateTime': end}}, timeout=(5, 15))
            response.raise_for_status()
        except requests.RequestException:
            raise Unavailable('Calendar rescheduling could not be confirmed.') from None
