"""Lead, quotation, unanswered inquiry, and workshop follow-up workflow helpers."""
from .followups import collect, refresh_message, queue_message, consent, set_consent, within_working_hours

LEAD_FOLLOWUP_KINDS = ('lead_followup', 'quotation_followup', 'unanswered_inquiry', 'workshop_ready')


def run_lead_followup_rule(db, cdb, scope, rule, today):
    if rule.kind not in LEAD_FOLLOWUP_KINDS:
        raise ValueError(f"Unsupported lead follow-up rule kind: {rule.kind}")
    return collect(db, cdb, scope, rule, today)
