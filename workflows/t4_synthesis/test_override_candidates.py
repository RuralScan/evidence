"""Check committed pending rules against their source-linked reference cases."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t4_synthesis import override_candidates as catalog, profiles


class PendingOverrides(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = {r['id']: r for r in catalog.records(catalog.DEFAULT)}
        cls.fmnr = cls.rows['agroforestry__regeneration_farmland__climate_override_v1']
        cls.context = dict(nbs_id='agroforestry',family_id='agroforestry__regeneration_farmland',
                           subpractice_id='fmnr',pathway='regeneration',host_state='present',
                           legal_state='clear',water_context='ordinary_rainfed')

    def test_generated_bytes_are_current_and_every_record_remains_pending(self):
        self.assertGreaterEqual(len(catalog.generate(check=True)), 4)
        self.assertTrue(all(r['status']=='pending' and r['activate'] is False for r in self.rows.values()))

    def test_source_csv_mutation_requires_regeneration(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/'overrides';shutil.copytree(catalog.DEFAULT,dest)
            p=dest/'overrides.csv';p.write_text(p.read_text().replace('Screen broad climatic hostility','Screen extreme climatic hostility'))
            with self.assertRaisesRegex(ValueError,'Stale generated'):
                catalog.generate(dest,check=True)

    def test_six_reference_climates_reproduce_prior_review_values(self):
        cases=json.loads((catalog.DEFAULT/'examples/climate_reference_checks.json').read_text())
        self.assertEqual(len(cases),6)
        for c in cases:
            with self.subTest(c=c['id']):
                actual=profiles.evaluate_candidate(self.rows[c['candidate']],c['values'],c['context'])
                self.assertAlmostEqual(actual['score'],c['expected_score'],places=12)
                self.assertEqual(actual['derived']['thermal_days'],c['expected_thermal_days'])
                self.assertAlmostEqual(actual['derived']['thermal_mean'],c['expected_thermal_mean'],places=12)
                self.assertFalse(actual['screen_reasons'])

    def test_fmnr_dry_screen_retains_tail_and_equality(self):
        low=profiles.evaluate_candidate(self.fmnr,{'ai':.02,'monthly_tas':[25]*12},self.context)
        boundary=profiles.evaluate_candidate(self.fmnr,{'ai':.03,'monthly_tas':[25]*12},self.context)
        self.assertGreater(low['score'],0)
        self.assertIn('rainfed_ai_below_003',low['screen_reasons'])
        self.assertAlmostEqual(boundary['score'],.2)
        self.assertEqual(boundary['state'],'candidate_default_rainfed_opportunity')

    def test_retention_does_not_inherit_regeneration_screen(self):
        actual=profiles.evaluate_candidate(self.fmnr,{'ai':.001,'monthly_tas':[-30]*12},self.context|{'subpractice_id':'parkland_retention'})
        self.assertEqual(actual['state'],'outside_review_scope');self.assertIsNone(actual['score']);self.assertFalse(actual['screen_reasons'])

    def test_planted_system_has_no_hidden_point_two_aridity_cutoff(self):
        row=self.rows['agroforestry__planted_silvoarable__climate_override_v1']
        context=self.context|{'family_id':'agroforestry__planted_silvoarable','subpractice_id':'alley_cropping','pathway':'planted'}
        actual=profiles.evaluate_candidate(row,{'ai':.1,'monthly_tas':[25]*12},context)
        self.assertLess(actual['score'],.2);self.assertEqual(actual['state'],'candidate_default_rainfed_opportunity')

    def test_known_dry_exclusion_persists_with_unknown_cold(self):
        actual=profiles.evaluate_candidate(self.fmnr,{'ai':.02,'monthly_tas':None},self.context)
        self.assertIsNone(actual['score']);self.assertEqual(actual['state'],'outside_default_rainfed_opportunity')

    def test_water_refuge_cannot_rescue_severe_cold(self):
        actual=profiles.evaluate_candidate(self.fmnr,{'ai':.01,'monthly_tas':[-20]*12},self.context|{'water_context':'mapped_potential_refuge','water_evidence_ref':'reviewed-refuge'})
        self.assertEqual(actual['state'],'outside_default_component_screen');self.assertIsNone(actual['area_ha'])

    def test_mangrove_native_score_and_separate_area(self):
        row=self.rows['mangrove_restoration__tidal_coastal__archive_override_v1']
        context=dict(nbs_id='mangrove_restoration',family_id='mangrove_restoration__tidal_coastal',subpractice_id='ecological_mangrove_restoration',host_state='present',legal_state='clear',unit_id='11283186:v1:test-unit',spatial_relation='whole',geometry_valid=True)
        whole=profiles.evaluate_candidate(row,{'overall_score':.6,'restorable_km2':1},context)
        partial=profiles.evaluate_candidate(row,{'overall_score':.6,'restorable_km2':1},context|{'spatial_relation':'partial'})
        self.assertEqual(whole['score'],.6);self.assertEqual(whole['area_ha'],100)
        self.assertIsNone(partial['area_ha']);self.assertEqual((partial['area_lower_ha'],partial['area_upper_ha']),(0,100))
        item={'values':{'overall_score':.6,'restorable_km2':1},'context':context}
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            profiles.evaluate_units(row['profile'],[item,copy.deepcopy(item)])

    def test_candidate_cannot_claim_acceptance(self):
        row=copy.deepcopy(self.fmnr);row['activate']=True
        with self.assertRaises(ValueError):profiles.validate_candidate(row)
        row['activate']=False;row['status']='accepted'
        with self.assertRaises(ValueError):profiles.validate_candidate(row)

if __name__=='__main__':unittest.main()
