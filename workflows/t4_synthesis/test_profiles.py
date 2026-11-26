"""Synthetic reference encodings, not evidence or accepted scientific policies."""
import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t4_synthesis import profiles, core


def climate():
    def definition(variable, unit, limits):
        return dict(variable=variable, dataset_id=variable + "_dataset", unit=unit, valid_range=limits)
    return dict(type="composite_scoping", unit="dimensionless", missing=None,
        scope=[dict(nbs_id="practice", family_id="family", subpractice_ids=["regeneration"], pathways=["regeneration"])],
        inputs={"aridity": definition("aridity", "dimensionless", [0, 100]),
                "monthly": definition("monthly", "degC", [-100, 70]),
                "mean": definition("mean", "degC", [-100, 70]),
                "days": definition("days", "days", [0, 365])},
        thermal_season=dict(kind="periodic_monthly_temperature_season", input="monthly", mean_output="mean", days_output="days",
            month_lengths=[31,28,31,30,31,30,31,31,30,31,30,31], threshold=0.9, operator="ge", empty_season_score=0),
        score=dict(kind="minimum", children=[dict(kind="log_logistic", input="aridity", x20=0.03, x80=0.2),
            dict(kind="minimum", children=[dict(kind="logistic", input="mean", x20=3, x80=10),
                                           dict(kind="log_logistic", input="days", x20=30, x80=130)])]),
        screens=[dict(id="dry", input="aridity", operator="lt", threshold=0.03, water_bypass=True),
                 dict(id="cold_mean", input="mean", operator="lt", threshold=3, water_bypass=False),
                 dict(id="cold_days", input="days", operator="lt", threshold=30, water_bypass=False)],
        water_policy="conditional_unscored", combined_score_cutoff=None, weight=None)


def context():
    return dict(nbs_id="practice", family_id="family", subpractice_id="regeneration", pathway="regeneration",
                host_state="present", legal_state="clear", water_context="ordinary_rainfed")


def unit_profile():
    return dict(type="precomputed_unit_index", unit="dimensionless", missing=None,
        scope=[dict(nbs_id="practice", family_id="family", subpractice_ids=None, pathways=None)],
        inputs={"score":dict(variable="score", dataset_id="dataset", unit="dimensionless",valid_range=[0,1]),
                "area":dict(variable="area",dataset_id="dataset",unit="km2",valid_range=[0,1e8])},
        score_input="score",area_input="area",area_to_hectares=100,area_policy="whole_units_partial_bounds_no_prorating")


class Profiles(unittest.TestCase):
    def test_exact_anchors_tails_and_no_negative_log_input(self):
        for kind, lo, hi in [("logistic",3,10),("log_logistic",0.03,0.2)]:
            self.assertAlmostEqual(profiles.smooth(kind,lo,hi,lo),.2)
            self.assertAlmostEqual(profiles.smooth(kind,lo,hi,hi),.8)
            self.assertEqual(profiles.smooth(kind,lo,hi,None),None)
            self.assertGreater(profiles.smooth(kind,lo,hi,1e308),.999)
        self.assertEqual(profiles.smooth("logistic",3,10,-1e308),0)
        self.assertAlmostEqual(profiles.smooth("logistic",1e-309,2e-309,1e-309),.2)
        self.assertAlmostEqual(profiles.smooth("logistic",1e-309,2e-309,2e-309),.8)
        self.assertEqual(profiles.smooth("log_logistic",.03,.2,0),0)
        for x in (-1,True,float("nan"),float("inf")):
            with self.subTest(x=x), self.assertRaises(ValueError):
                profiles.smooth("log_logistic",.03,.2,x)

    def test_sahel_like_regeneration_uses_minimum_not_product(self):
        p=climate(); r=profiles.evaluate_profile(p,dict(aridity=.2,monthly=[28]*12),context())
        self.assertAlmostEqual(r["score"],.8)
        self.assertEqual(r["derived"],dict(mean=28,days=365))
        self.assertEqual(r["state"],"candidate_default_rainfed_opportunity")
        self.assertIsNone(r["area_ha"])

    def test_dry_screen_equality_and_tailing_score(self):
        p=climate()
        for x,state in [(.029,"outside_default_rainfed_opportunity"),(.03,"candidate_default_rainfed_opportunity")]:
            r=profiles.evaluate_profile(p,dict(aridity=x,monthly=[28]*12),context())
            self.assertEqual(r["state"],state)
            self.assertGreater(r["score"],0)

    def test_empty_thermal_season_distinct_from_missing(self):
        p=climate()
        empty=profiles.evaluate_profile(p,dict(aridity=.2,monthly=[-10]*12),context())
        self.assertEqual(empty["score"],0)
        self.assertEqual(empty["derived"],dict(mean=None,days=0))
        self.assertEqual(empty["screen_reasons"],["cold_days"])
        missing=profiles.evaluate_profile(p,dict(aridity=.2),context())
        self.assertIsNone(missing["score"])
        self.assertEqual(missing["state"],"unknown_climate")
        self.assertEqual(missing["derived"],dict(mean=None,days=None))

    def test_unknown_component_does_not_hide_known_exclusion(self):
        r=profiles.evaluate_profile(climate(),dict(monthly=[-10]*12),context())
        self.assertIsNone(r["score"])
        self.assertEqual(r["state"],"outside_default_component_screen")

    def test_water_refuge_conditional_cannot_rescue_cold_or_legal(self):
        c=context()|dict(water_context="mapped_potential_refuge",water_evidence_ref="mapped context")
        for temp,legal,state in [(28,"clear","conditional_water_pathway_unscored"),(-10,"clear","outside_default_component_screen"),(28,"excluded","excluded_existing_gate")]:
            r=profiles.evaluate_profile(climate(),dict(aridity=.01,monthly=[temp]*12),c|dict(legal_state=legal))
            self.assertEqual(r["state"],state);self.assertIsNone(r["score"]);self.assertIsNone(r["area_ha"])
        with self.assertRaises(ValueError):
            profiles.evaluate_profile(climate(),{},context()|dict(water_context="mapped_potential_refuge"))

    def test_retention_unknown_pathway_other_family_outside_scope(self):
        for change in (dict(subpractice_id="retention"),dict(pathway=None),dict(family_id="other")):
            r=profiles.evaluate_profile(climate(),dict(aridity=0,monthly=[-10]*12),context()|change)
            self.assertEqual(r["state"],"outside_review_scope");self.assertIsNone(r["score"]);self.assertEqual(r["screen_reasons"],[])

    def test_unknown_water_context_is_not_default_rainfed_opportunity(self):
        r=profiles.evaluate_profile(climate(),dict(aridity=.2,monthly=[28]*12),context()|dict(water_context="unknown"))
        self.assertEqual(r["state"],"climate_pass_water_context_unresolved")
        self.assertAlmostEqual(r["score"],.8)

    def test_periodic_month_midpoint_and_annual_wrap(self):
        t=climate()["thermal_season"]
        daily=profiles.monthly_to_daily(list(range(12)),t["month_lengths"])
        self.assertEqual(len(daily),365);self.assertEqual(daily[15],0)
        self.assertGreater(daily[0],0);self.assertGreater(daily[-1],0)
        self.assertIsNone(profiles.monthly_to_daily([None]+[1]*11,t["month_lengths"]))

    def test_invalid_input_or_substituted_metrics_cannot_be_scored(self):
        for values in (dict(monthly=[True]*12),dict(monthly=[71]*12),dict(monthly=[1]*11),dict(mean=7),dict(unknown=1),dict(aridity=float("nan"))):
            with self.subTest(values=values),self.assertRaises(ValueError):
                profiles.evaluate_profile(climate(),values,context())

    def test_arbitrary_expression_product_cutoff_and_water_cold_bypass_rejected(self):
        for key,value in [("score",dict(kind="product",children=[])),("combined_score_cutoff",.2),("weight",1),("expression","arbitrary")]:
            p=climate();p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):profiles.validate_profile(p)
        p=climate();p["screens"][1]["water_bypass"]=True
        with self.assertRaises(ValueError):profiles.validate_profile(p)

    def test_unit_identity_area_bounds_zero_and_unknown(self):
        p=unit_profile();c=context()|dict(unit_id="release:unit",spatial_relation="whole",geometry_valid=True)
        r=profiles.evaluate_profile(p,dict(score=.4,area=2),c)
        self.assertEqual((r["score"],r["area_ha"],r["area_lower_ha"],r["area_upper_ha"]),(.4,200,200,200))
        r=profiles.evaluate_profile(p,dict(score=.4,area=2),c|dict(spatial_relation="partial"))
        self.assertEqual((r["area_ha"],r["area_lower_ha"],r["area_upper_ha"]),(None,0,200))
        r=profiles.evaluate_profile(p,dict(score=0,area=0),c)
        self.assertEqual(r["state"],"no_modelled_restorable_area");self.assertIsNone(r["score"])
        for values in ({},dict(score=.4)):
            self.assertEqual(profiles.evaluate_profile(p,values,c)["state"],"unknown")
        for geometry,state in [(None,"unknown_geometry"),(False,"invalid_geometry")]:
            self.assertEqual(profiles.evaluate_profile(p,dict(score=.4,area=2),c|dict(geometry_valid=geometry))["state"],state)

    def test_unit_invalid_values_mismatch_duplicate_and_gates(self):
        p=unit_profile();c=context()|dict(unit_id="unit",spatial_relation="whole",geometry_valid=True)
        for values in (dict(score=0,area=1),dict(score=.4,area=0),dict(score=1.01,area=1),dict(score=.4,area=-1),dict(score=True,area=1)):
            with self.subTest(values=values),self.assertRaises(ValueError):profiles.evaluate_profile(p,values,c)
        record=dict(values=dict(score=.4,area=2),context=c)
        with self.assertRaises(ValueError):profiles.evaluate_units(p,[record,record])
        r=profiles.evaluate_profile(p,record["values"],c|dict(legal_state="excluded"))
        self.assertEqual(r["state"],"excluded_existing_gate");self.assertIsNone(r["area_ha"])

    def test_known_gate_survives_missing_unit_data_and_mixed_release_rejected(self):
        p=unit_profile();c=context()|dict(unit_id="unit",spatial_relation="whole",geometry_valid=True,legal_state="excluded")
        for values,geometry in [({},True),({},None),({},False),(dict(score=0,area=0),True)]:
            r=profiles.evaluate_profile(p,values,c|dict(geometry_valid=geometry))
            self.assertEqual(r["state"],"excluded_existing_gate")
        p["inputs"]["area"]["dataset_id"]="different_release"
        with self.assertRaises(ValueError):profiles.validate_profile(p)

    def test_draft_cannot_claim_acceptance(self):
        record=dict(format="ruralscan.t4-profile-candidate.v1",id="synthetic",status="pending",activate=False,profile=climate(),
            justification={k:"Synthetic only" for k in "rationale mechanism source_relationship analyst_choices transfer_limits binding area_accounting replacement_policy approval_remaining".split()},evidence_refs=[dict(source_id="synthetic",citation="Synthetic test",url="https://example.invalid/source",locator="section",claim_role="test",admission_status="pending")])
        profiles.validate_candidate(record)
        for change in (dict(status="accepted"),dict(activate=True),dict(evidence_ids=["invented"])):
            with self.assertRaises(ValueError):profiles.validate_candidate(record|change)

    def test_structured_boundary_requirements_and_scalar_core_extension(self):
        p=climate();c=context()
        samples=[({},c),({},c|dict(pathway=None)),(dict(aridity=.2,monthly=[28]*12),c),
                 (dict(aridity=.2,monthly=[28]*12),c|dict(legal_state="excluded")),
                 (dict(aridity=.01,monthly=[28]*12),c),
                 (dict(aridity=.2,monthly=[2]*12),c),(dict(aridity=.2,monthly=[-10]*12),c),
                 (dict(aridity=.2,monthly=[28]*12),c|dict(water_context="mapped_potential_refuge",water_evidence_ref="test"))]
        cases=[dict(input=dict(values=v,context=ctx),expected=profiles.evaluate_profile(p,v,ctx),reason="Synthetic branch") for v,ctx in samples]
        row=dict(relationship_type="composite_scoping",relationship_params=p,weight_default=None,justification=dict(boundary_cases=cases))
        core.representation(row)
        row["justification"]["boundary_cases"]=cases[:2]
        with self.assertRaises(ValueError):core.representation(row)
        for kind,lo,hi in [("logistic",3,10),("log_logistic",.03,.2)]:
            values=[None,0,lo,(lo+hi)/2,hi,hi*2]
            params=dict(unit="test",missing=None,x20=lo,x80=hi)
            row=dict(relationship_type=kind,relationship_params=params,readiness="calibrated",justification=dict(boundary_cases=[
                dict(input=v,expected=core.evaluate(kind,params,v),reason="Synthetic endpoint") for v in values]))
            core.representation(row)

    def test_unadopted_definitions_and_unregistered_scope_block_official_mapping(self):
        p=climate()
        defs={"schema/registers/FAM_family_registry.csv":[dict(nbs_id="practice",suitability_family_id="family",subpractice_id="regeneration")],
              "schema/registers/VONT_variable_ontology.csv":[],"schema/T1_data_registry.csv":[],"schema/registers/BIND_dataset_binding.csv":[]}
        with self.assertRaisesRegex(ValueError,"Unadopted"):
            profiles.validate_definitions(p,defs,"practice","family",dict(scope_type="global",scope_id=""))
        for d in p["inputs"].values():
            defs["schema/registers/VONT_variable_ontology.csv"].append(dict(canonical_variable_id=d["variable"],canonical_unit=d["unit"]))
            defs["schema/T1_data_registry.csv"].append(dict(dataset_id=d["dataset_id"]))
            defs["schema/registers/BIND_dataset_binding.csv"].append(dict(variable=d["variable"],dataset_id=d["dataset_id"],scope_type="global",scope_id="",preference_rank="1",status="catalogued"))
        profiles.validate_definitions(p,defs,"practice","family",dict(scope_type="global",scope_id=""))
        defs["schema/registers/BIND_dataset_binding.csv"].pop()
        with self.assertRaisesRegex(ValueError,"No pinned"):
            profiles.validate_definitions(p,defs,"practice","family",dict(scope_type="global",scope_id=""))


if __name__ == "__main__":unittest.main()
