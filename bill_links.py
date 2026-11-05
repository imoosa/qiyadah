"""Expiring, company-bound customer bill links."""
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadData


def issue_bill_token(company_id, job_id):
    return URLSafeTimedSerializer(current_app.secret_key, salt='workshop-bill-v1').dumps(
        {'company_id': str(company_id), 'job_id': int(job_id)})


def verify_bill_token(token, job_id):
    try:
        data = URLSafeTimedSerializer(current_app.secret_key, salt='workshop-bill-v1').loads(token, max_age=7*86400)
        if not isinstance(data, dict) or data.get('job_id') != int(job_id) or not data.get('company_id'):
            raise ValueError()
        return data['company_id']
    except (BadData, ValueError, TypeError):
        raise ValueError('This bill link is invalid or expired. Request a new link from the workshop.') from None
