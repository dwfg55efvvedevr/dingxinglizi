from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_findings import merge_findings, validate_finding  # noqa: E402


TARGET = "a" * 40
SHARD = {"shard_id": "SHARD-0001", "files": ["src/auth.py"]}


def finding(identifier: str, severity: str = "P1", title: str = "Missing authorization") -> dict:
    return {
        "finding_id": identifier,
        "shard_id": "SHARD-0001",
        "target_fingerprint": TARGET,
        "path": "src/auth.py",
        "start_line": 10,
        "end_line": 12,
        "severity": severity,
        "category": "security",
        "rule_id": "AUTH-01",
        "title": title,
        "description": "The endpoint does not enforce authorization.",
        "evidence": "The handler calls the service without a policy check.",
        "recommendation": "Apply the policy before the service call.",
        "status": "OPEN",
        "confidence": "HIGH",
    }


class ReviewFindingTests(unittest.TestCase):
    def test_strict_path_target_and_shard_lineage(self) -> None:
        valid = validate_finding(finding("FIND-AUTH-001"), shard=SHARD, target_fingerprint=TARGET)
        self.assertEqual(valid["path"], "src/auth.py")
        outside = finding("FIND-AUTH-002")
        outside["path"] = "../secret.txt"
        with self.assertRaisesRegex(ValueError, "unsafe"):
            validate_finding(outside, shard=SHARD, target_fingerprint=TARGET)
        wrong_target = finding("FIND-AUTH-003")
        wrong_target["target_fingerprint"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "target fingerprint"):
            validate_finding(wrong_target, shard=SHARD, target_fingerprint=TARGET)
        wrong_shard = finding("FIND-AUTH-004")
        wrong_shard["shard_id"] = "SHARD-0002"
        with self.assertRaisesRegex(ValueError, "shard lineage"):
            validate_finding(wrong_shard, shard=SHARD, target_fingerprint=TARGET)

    def test_exact_duplicate_is_merged_with_lineage(self) -> None:
        first = validate_finding(finding("FIND-AUTH-101"), shard=SHARD, target_fingerprint=TARGET)
        second_value = finding("FIND-AUTH-102")
        second = validate_finding(second_value, shard=SHARD, target_fingerprint=TARGET)
        merged = merge_findings([first, second])
        self.assertEqual(merged["input_count"], 2)
        self.assertEqual(merged["merged_count"], 1)
        self.assertEqual(merged["findings"][0]["source_finding_ids"], ["FIND-AUTH-101", "FIND-AUTH-102"])

    def test_severity_conflict_is_preserved(self) -> None:
        first = validate_finding(finding("FIND-AUTH-201", severity="P0"), shard=SHARD, target_fingerprint=TARGET)
        second = validate_finding(finding("FIND-AUTH-202", severity="P2"), shard=SHARD, target_fingerprint=TARGET)
        merged = merge_findings([first, second])
        self.assertEqual(merged["merged_count"], 2)
        self.assertEqual(len(merged["severity_conflicts"]), 1)
        self.assertTrue(all("severity_conflict_id" in item for item in merged["findings"]))

    def test_possible_duplicate_is_kept_not_silently_merged(self) -> None:
        first = validate_finding(finding("FIND-AUTH-301"), shard=SHARD, target_fingerprint=TARGET)
        second = validate_finding(
            finding("FIND-AUTH-302", title="Authorization policy not applied"),
            shard=SHARD, target_fingerprint=TARGET,
        )
        merged = merge_findings([first, second])
        self.assertEqual(merged["merged_count"], 2)
        self.assertEqual(len(merged["possible_duplicates"]), 1)
        self.assertTrue(all(item.get("possible_duplicate_refs") for item in merged["findings"]))


if __name__ == "__main__":
    unittest.main()
