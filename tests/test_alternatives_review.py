import json
import unittest
from pathlib import Path

from digcon.config import default_config
from digcon.domain.models import AlternativesReview, AssessmentState
from digcon.domain.alternatives import fingerprint, ready
from digcon.engine import run_engine
from digcon.reporting.json_report import dumps, assessment_of
from engine_support import build_state, CTX, load_yaml, expectation_failures


def reviewed(existence='YES', decision='SUFFICIENT'):
    state = build_state()
    state.alternatives_review = AlternativesReview(
        existence=existence, comparison='Compare manual processing and narrower use against the purpose.',
        evidence_refs=['addendum:section-3'], reviewer='Human reviewer', review_date='2026-10-25',
        review_reason='Case-specific evaluation of suitability and interference.', decision=decision)
    state.alternatives_review.reviewed_fingerprint = fingerprint(state)
    return state


class AlternativesTests(unittest.TestCase):
    def result(self, state):
        return run_engine(default_config(), state, CTX)

    def test_both_yes_and_no_can_support_necessity_after_review(self):
        for existence in ('YES', 'NO'):
            state = reviewed(existence)
            result = self.result(state)
            self.assertEqual(result.prop_statuses['PROP-03'].value, 'SUPPORTED')
            self.assertEqual(result.outcome.value, 'O1')

    def test_no_does_not_become_missing_analysis(self):
        state = reviewed('NO')
        state.answers['C31'].state = 'NO'
        state.alternatives_review.reviewed_fingerprint = fingerprint(state)
        self.assertEqual(self.result(state).outcome.value, 'O1')

    def test_unjustified_exclusion_requires_revision(self):
        result = self.result(reviewed('YES', 'UNJUSTIFIED_EXCLUSION'))
        self.assertEqual(result.outcome.value, 'O3')
        self.assertIn('PROP-03', [f.rule_id for f in result.open_remediations])
        self.assertNotIn('PROP-03', [f.rule_id for f in result.evidence_gaps])

    def test_missing_or_unrecorded_review_keeps_evidence_gap(self):
        for decision in ('PENDING', 'MISSING_EVIDENCE'):
            self.assertEqual(self.result(reviewed('YES', decision)).outcome.value, 'O4')
        state = reviewed()
        state.alternatives_review.reviewed_fingerprint = ''
        self.assertEqual(self.result(state).outcome.value, 'O4')

    def test_empty_evidence_and_contradictory_conclusion_are_not_approved(self):
        state = reviewed()
        state.alternatives_review.evidence_refs = []
        state.alternatives_review.reviewed_fingerprint = fingerprint(state)
        self.assertFalse(ready(state.alternatives_review))
        self.assertEqual(self.result(state).outcome.value, 'O4')
        self.assertFalse(ready(reviewed('NO', 'UNJUSTIFIED_EXCLUSION').alternatives_review))

    def test_changed_comparison_or_context_requires_new_review(self):
        state = reviewed()
        state.alternatives_review.comparison = 'Different options'
        self.assertEqual(self.result(state).outcome.value, 'O4')
        state = reviewed()
        state.answers['C01'].value = 'A different system'
        self.assertEqual(self.result(state).outcome.value, 'O4')

    def test_export_roundtrip_preserves_meanings_and_review(self):
        state = reviewed('NO')
        restored = AssessmentState.model_validate(assessment_of(json.loads(dumps(state, self.result(state)))))
        self.assertEqual(restored.alternatives_review.existence, 'NO')
        self.assertEqual(restored.answers['C31'], state.answers['C31'])
        self.assertEqual(self.result(restored), self.result(state))

    def test_legacy_answer_is_not_reinterpreted(self):
        for value, expected in [('YES', 'O1'), ('NO', 'O4'), ('UNKNOWN', 'O4')]:
            state = build_state({'answers': {'C31': value}})
            raw = state.model_dump(mode='json'); raw.pop('alternatives_review')
            restored = AssessmentState.model_validate(raw)
            self.assertIsNone(restored.alternatives_review)
            self.assertEqual(self.result(restored).outcome.value, expected)

    def test_existing_workbook_cases(self):
        count = 0
        for path in sorted((Path(__file__).parent / 'fixtures').glob('*.yaml')):
            fixtures = load_yaml(path.name)
            if not isinstance(fixtures, list):
                continue
            for fixture in fixtures:
                if 'expect' not in fixture or 'patch' not in fixture:
                    continue
                with self.subTest(fixture=fixture['id']):
                    errors = expectation_failures(self.result(build_state(fixture['patch'])), fixture)
                    self.assertEqual(errors, [])
                    count += 1
        self.assertGreaterEqual(count, 40)


if __name__ == '__main__':
    unittest.main()
