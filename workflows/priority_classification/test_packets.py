import copy
import json
from pathlib import Path
import unittest
from check import validate


class Packets(unittest.TestCase):
    def setUp(self):
        self.packets = [json.loads(p.read_text()) for p in (Path(__file__).parent / "packets").glob("*.json")]

    def test_all_source_packets(self):
        self.assertEqual(len(self.packets), 5)
        for packet in self.packets:
            self.assertEqual(len(validate(packet)), 64)

    def test_no_claimed_approval_or_register_identity(self):
        for key, value in [("status", "accepted"), ("canonical_source_id", "src_fake"), ("decision", "keep")]:
            packet = copy.deepcopy(self.packets[0]); packet[key] = value
            with self.assertRaises(ValueError): validate(packet)

    def test_locator_and_source_tampering_change_identity(self):
        packet = copy.deepcopy(self.packets[0]); before = validate(packet)
        packet["source"]["artifact_sha256"] = "f" * 64
        self.assertNotEqual(before, validate(packet))
        packet["source"]["locator"] = ""
        with self.assertRaises(ValueError): validate(packet)

    def test_source_findings_are_not_method_scores(self):
        packet = copy.deepcopy(self.packets[0]); packet["classification_scores"] = [0, .33, .66, 1]
        with self.assertRaises(ValueError): validate(packet)


if __name__ == "__main__": unittest.main()
