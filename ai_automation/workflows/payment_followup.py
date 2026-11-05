"""Sales invoice and eShip freight payment reminder workflow helpers."""
from .followups import collect, refresh_message, queue_message, consent, set_consent, within_working_hours

PAYMENT_FOLLOWUP_KINDS = ('payment_due', 'payment_overdue', 'eship_payment_due', 'eship_freight_overdue')


def run_payment_followup_rule(db, cdb, scope, rule, today):
    if rule.kind not in PAYMENT_FOLLOWUP_KINDS:
        raise ValueError(f"Unsupported payment follow-up rule kind: {rule.kind}")
    return collect(db, cdb, scope, rule, today)
