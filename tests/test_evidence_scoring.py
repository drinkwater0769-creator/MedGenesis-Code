import json
import tempfile
import unittest
from pathlib import Path

from clinicalrepbench.analysis_evidence import check_analysis_evidence
from clinicalrepbench.evaluate import score_metrics, score_submission, _score_rubric_check
from test_figure2d_scoring_calibration import write_static_submission

ROOT = Path(__file__).resolve().parents[1]


class EvidenceScoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'artifacts/tables').mkdir(parents=True)
        (self.root / 'code').mkdir()
        (self.root / 'code/analysis.py').write_text('estimate = 1.4\n')

    def evidence(self, check, kind, csv_text, **overrides):
        (self.root / 'artifacts/tables/results.csv').write_text(csv_text)
        entry = {'status': 'completed', 'kind': kind, 'code_path': 'code/analysis.py',
                 'result_path': 'artifacts/tables/results.csv', **overrides}
        (self.root / 'artifacts/analysis_evidence.json').write_text(json.dumps({
            'schema_version': 'clinicalrep.analysis-evidence.v1', 'checks': {check: entry}}))

    def test_prose_and_negated_keyword_mentions_are_not_results(self):
        for check in ['effect_uncertainty_reported', 'sensitivity_analysis', 'uncertainty_or_sensitivity']:
            for text in ['No confidence intervals. No full sensitivity analysis.',
                         'We conducted sensitivity analysis; confidence interval and 95%.',
                         '原论文报告了置信区间，本次未做敏感性分析。']:
                self.assertFalse(check_analysis_evidence(check, self.root, text)[0])

    def test_valid_uncertainty_can_pass(self):
        self.evidence('effect_uncertainty_reported', 'uncertainty',
                      'metric_id,estimate,ci_lower,ci_upper\neffect,1.4,1.1,1.8\n')
        self.assertTrue(check_analysis_evidence('effect_uncertainty_reported', self.root,
                                               'Our estimate and interval are in the results table.')[0])

    def test_denial_overrides_completed_manifest(self):
        self.evidence('effect_uncertainty_reported', 'uncertainty',
                      'metric_id,estimate,ci_lower,ci_upper\neffect,1.4,1.1,1.8\n')
        for text in ['No confidence intervals were computed.', 'Confidence intervals were not computed.',
                     'We did not compute confidence intervals.', '本次未计算置信区间。']:
            self.assertFalse(check_analysis_evidence('effect_uncertainty_reported', self.root, text)[0], text)

    def test_invalid_and_degenerate_intervals_fail(self):
        for low, high in [('nan', '2'), ('1.8', '1.1'), ('1.4', '1.4'), ('1.5', '1.8')]:
            self.evidence('effect_uncertainty_reported', 'uncertainty',
                          f'metric_id,estimate,ci_lower,ci_upper\neffect,1.4,{low},{high}\n')
            self.assertFalse(check_analysis_evidence('effect_uncertainty_reported', self.root, '')[0])

    def test_sensitivity_requires_primary_and_alternative_for_same_metric(self):
        self.evidence('sensitivity_analysis', 'sensitivity',
                      'metric_id,analysis_id,estimate\neffect,primary,1.4\neffect,complete_case,1.3\n')
        self.assertTrue(check_analysis_evidence('sensitivity_analysis', self.root, '')[0])
        self.assertFalse(check_analysis_evidence('sensitivity_analysis', self.root,
                                                'No full sensitivity analysis was completed.')[0])
        for rows in ['effect,primary,1.4\n', 'effect,primary,1.4\nother,alternative,1.3\n',
                     'effect,primary,1.4\neffect,primary,1.3\n']:
            self.evidence('sensitivity_analysis', 'sensitivity', 'metric_id,analysis_id,estimate\n' + rows)
            self.assertFalse(check_analysis_evidence('sensitivity_analysis', self.root, '')[0])

    def test_evidence_cannot_escape_submission(self):
        self.evidence('effect_uncertainty_reported', 'uncertainty',
                      'metric_id,estimate,ci_lower,ci_upper\neffect,1.4,1.1,1.8\n',
                      code_path='../outside.py')
        self.assertFalse(check_analysis_evidence('effect_uncertainty_reported', self.root, '')[0])

    def test_incomplete_status_fails(self):
        self.evidence('effect_uncertainty_reported', 'uncertainty',
                      'metric_id,estimate,ci_lower,ci_upper\neffect,1.4,1.1,1.8\n', status='planned')
        self.assertFalse(check_analysis_evidence('effect_uncertainty_reported', self.root, '')[0])

    def test_negative_clinical_safety_statement_still_counts(self):
        check = {'id': 'clinical_safety_boundary', 'source': 'report', 'any': ['not actionable']}
        self.assertTrue(_score_rubric_check(check, {'root': self.root, 'report_text': 'This is not actionable.'})[0])

    def test_nan_infinity_boolean_and_missing_are_zero_and_kept_in_denominator(self):
        target = {'metrics': [{'id': str(i), 'value': 2, 'tolerance_abs': .1, 'weight': 1} for i in range(5)]}
        result = score_metrics(target, {'metrics': {'0': float('nan'), '1': float('inf'), '2': True, '4': 2}})
        self.assertEqual(result['objective_score'], .2)
        self.assertEqual(sum(d['valid_numeric_submission'] for d in result['details']), 1)
        json.dumps(result, allow_nan=False)

    def test_missing_models_cap_same_denominator_even_with_extra_metrics(self):
        task = ROOT / 'tasks/Endocrinology_001'
        write_static_submission(task, self.root)
        metric_file = self.root / 'artifacts/primary_metrics.json'
        data = json.loads(metric_file.read_text())
        ids = list(data['metrics'])
        data['metrics'] = {ids[0]: data['metrics'][ids[0]], 'unrelated_bonus': 100}
        metric_file.write_text(json.dumps(data))
        result = score_submission(task, self.root)
        self.assertEqual(result['numeric_metric_coverage'], .125)
        self.assertLessEqual(result['final_score'], .125)
        self.assertEqual(len(result['metrics']), 8)

    def test_invalid_submissions_also_have_protocol_and_eligibility(self):
        result = score_submission(ROOT / 'tasks/Endocrinology_001', self.root)
        self.assertFalse(result['ok'])
        self.assertEqual(result['score_protocol'], 'local-rubric-v3-evidence')
        self.assertFalse(result['formal_score_eligible'])
        self.assertIsNone(result['ranking_score'])

if __name__ == '__main__':
    unittest.main()
