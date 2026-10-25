"""Versioned alternatives assessment; legacy C31 keeps its original meaning."""
import hashlib
import json
from datetime import date


def fingerprint(state):
    record = state.alternatives_review
    if record is None:
        return ''
    data = record.model_dump(mode='json')
    for key in ('reviewed_fingerprint', 'history'):
        data.pop(key, None)
    # Revisit the determination when source answers, including purpose, change.
    payload = {'record': data, 'answers': {k: v.model_dump(mode='json') for k, v in state.answers.items()},
               'risks': {k: v.model_dump(mode='json') for k, v in state.risks.items()}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def ready(record):
    if not record or record.decision == 'PENDING':
        return False
    try:
        date.fromisoformat(record.review_date)
    except ValueError:
        return False
    if not record.reviewer.strip() or not record.review_reason.strip():
        return False
    if record.decision == 'MISSING_EVIDENCE':
        return True
    if record.existence not in ('YES', 'NO') or not record.comparison.strip() or not record.evidence_refs:
        return False
    # An unjustified exclusion entails that a relevant alternative exists.
    return record.decision != 'UNJUSTIFIED_EXCLUSION' or record.existence == 'YES'


def decision(state):
    record = state.alternatives_review
    if record is None:
        return None  # retain legacy assessment semantics
    if not ready(record) or record.reviewed_fingerprint != fingerprint(state):
        return 'MISSING_EVIDENCE'
    return record.decision
