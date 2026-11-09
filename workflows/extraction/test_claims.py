import unittest

from claims import build_unit, RULESET


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(
            nbs_id="water_harvesting_conservation",
            suitability_family_id="water_harvesting__terracing",
            variable="annual_precipitation",
            use_role="structural_suitability",
        )
        self.quote = (
            "Terraces were observed where annual rainfall was 200- 600 mm/year."
        )
        self.draft = dict(
            evidence_id="ev_demo",
            raw_name="annual rainfall",
            evidence_type="literature_relationship",
            claim_scope="practice_technology",
            claim_basis="expert_assertion",
            extraction_confidence="medium",
            context={
                "practice_as_described": "Terraces",
                "reported_values": {"low": 200, "high": 600, "unit": "mm/year"},
                "calibration_hold": "Only observed settings are documented.",
            },
            relationship={"direction": "unclear"},
        )

    def build(self):
        return build_unit(self.draft, self.scope, "manual", self.quote, 129)

    def test_current_observation_keeps_source_numbers_private_to_context(self):
        unit = self.build()
        self.assertFalse(unit["reviewer_ok"])
        self.assertEqual(unit["relationship"], {"direction": "unclear"})
        self.assertEqual(unit["ruleset_version"], RULESET)
        self.assertEqual(unit["page"], 129)
        self.draft["context"]["reported_values"]["high"] = 70
        self.assertEqual(unit["context"]["reported_values"]["high"], 600)

    def test_disallow_scope_or_review_override(self):
        for key, value in (
            ("page", 1),
            ("source_id", "other"),
            ("ruleset_version", "v1.6.0"),
            ("reviewer_ok", True),
            ("review_state", "dropped"),
            ("variable", "slope"),
            ("evidence_id", True),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_unit(
                    self.draft | {key: value}, self.scope, "manual", self.quote, 129
                )

    def test_no_numeric_curve_even_if_anchors_contain_endpoints(self):
        self.draft["relationship"]["abs_max"] = 600
        with self.assertRaisesRegex(ValueError, "source_check.parameters"):
            self.build()

    def test_source_parameters_classes_and_weights_are_retainable(self):
        threshold = "Minimum required depth is 30 cm."
        table = "Depth classes: poor <30 rank 1; suitable ≥30 rank 2."
        weight = "The AHP weight for depth was 10.5%."
        self.quote = " ".join([threshold, table, weight])
        self.draft["relationship"] = {
            "direction": "increasing",
            "abs_min": 30,
            "unit": "cm",
            "classes": [
                {"label": "poor", "range": "<30", "rank": 1},
                {"label": "suitable", "range": "≥30", "rank": 2},
            ],
            "ahp_weight_pct": 10.5,
        }
        self.draft["context"] = {
            "practice_as_described": "terraces",
            "calibration_hold": "Source classes and weights apply only to the local design.",
            "source_check": {
                "parameters": threshold,
                "classes": table,
                "weight": weight,
            },
        }
        result = self.build()
        self.assertEqual(
            result["relationship"]["classes"], self.draft["relationship"]["classes"]
        )
        self.assertFalse(result["reviewer_ok"])
        self.draft["context"]["source_check"]["weight"] = table
        with self.assertRaisesRegex(ValueError, "missing from quote"):
            self.build()

    def test_observation_cannot_become_threshold_by_copying_its_quote(self):
        self.draft["relationship"].update(abs_max=600, unit="mm/year")
        self.draft["context"]["source_check"] = {"parameters": self.quote}
        with self.assertRaisesRegex(ValueError, "Observed-use excerpt"):
            self.build()

    def test_percent_and_fraction_are_not_interchangeable(self):
        self.draft.update(
            relationship={"direction": "unclear", "ahp_weight_pct": 12},
            context={
                "practice_as_described": "terraces",
                "calibration_hold": "Local criterion weight.",
                "source_check": {"weight": "Weight 12; 4% of records were missing."},
            },
        )
        self.quote = self.draft["context"]["source_check"]["weight"]
        with self.assertRaisesRegex(ValueError, "Percentage"):
            self.build()

    def test_unknown_context_fields_cannot_smuggle_approvals(self):
        self.draft["context"]["approved_runtime_mapping"] = True
        with self.assertRaisesRegex(ValueError, "context"):
            self.build()

    def test_anchor_numbers_in_observed_values(self):
        for invalid in (350, True, float("inf"), float("nan"), "1,200 mm"):
            self.draft["context"]["reported_values"]["high"] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.build()

    def test_cited_and_species_claims_need_provenance(self):
        for tag, value, fix in (
            ("claim_basis", "cited_secondary", {"attribution": "Earlier field guide"}),
            ("claim_scope", "species_specific", {"taxon": "Example species"}),
        ):
            draft = self.draft | {tag: value}
            with self.assertRaises(ValueError):
                build_unit(draft, self.scope, "manual", self.quote, 129)
            unit = build_unit(draft | fix, self.scope, "manual", self.quote, 129)
            self.assertEqual(unit[tag], value)

    def test_effect_direction_and_signed_magnitude_anchored(self):
        self.scope.update(variable="erosion_hazard", use_role="nbs_effect")
        self.quote = (
            "Bench terraces reduced erosion. The measured change was −0.5 t/ha."
        )
        self.draft.update(
            relationship={
                "metric": "absolute",
                "outcome_raw": "erosion",
                "unit": "t/ha",
                "magnitude": -0.5,
                "direction": "negative",
                "direction_cue": "reduced erosion",
            },
            context={"practice_as_described": "Bench terraces"},
        )
        self.assertEqual(self.build()["relationship"]["direction"], "negative")
        self.draft["relationship"]["magnitude"] = 0.5
        with self.assertRaises(ValueError):
            self.build()
        self.draft["relationship"]["magnitude"] = -0.5
        self.draft["relationship"]["direction_cue"] = "lost erosion"
        with self.assertRaisesRegex(ValueError, "cue"):
            self.build()

    def test_page_and_quote_validated(self):
        for page, quote in ((True, self.quote), (0, self.quote), (1, "1")):
            with self.subTest(page=page), self.assertRaises(ValueError):
                build_unit(self.draft, self.scope, "manual", quote, page)

    def test_effects_cannot_invent_metrics(self):
        self.draft["context"] = {"practice_as_described": "terraces"}
        self.scope.update(use_role="nbs_effect")
        self.draft["relationship"] = {
            "metric": "percent_made_up",
            "outcome_raw": "erosion",
        }
        with self.assertRaisesRegex(ValueError, "metric"):
            self.build()


if __name__ == "__main__":
    unittest.main()
