"""End-to-end tests for the BasketryStitch command line tool.

Run with either runner:

    python3 -m unittest discover -s tests
    python3 -m pytest

Every test drives the real CLI in a throwaway directory (via --log), so no
test depends on the demo log shipped in the repository root.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import basketrystitch  # noqa: E402  (path set up above)

CLI = [sys.executable, str(ROOT / "basketrystitch.py")]

VALID_ADD = [
    "add",
    "--name",
    "Willow Coil",
    "--reed-width",
    "4",
    "--unit",
    "in",
    "--sample-rows",
    "10",
    "--row-height-before",
    "100",
    "--row-height-after",
    "88",
]


def run_cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run the real CLI and capture both streams."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("NO_COLOR", None)
    return subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        env=env,
        check=False,
    )


class CliTest(unittest.TestCase):
    """Common fixture: an isolated directory holding one log file."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name
        self.log = os.path.join(self.dir, "basketrystitch_log.json")

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return run_cli(*args, "--log", self.log)

    def add(self, *args: str) -> subprocess.CompletedProcess:
        return self.cli(*args)

    def read_log(self) -> dict:
        with open(self.log, encoding="utf-8") as stream:
            return json.load(stream)

    def add_valid(self) -> subprocess.CompletedProcess:
        result = self.cli(*VALID_ADD)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def assert_log_untouched(self, before: bytes) -> None:
        with open(self.log, "rb") as stream:
            self.assertEqual(stream.read(), before, "the log must stay byte-identical")


class AddCommandTests(CliTest):
    def test_first_add_creates_the_log_and_confirms(self) -> None:
        result = self.add_valid()

        self.assertIn("Added entry 1: Willow Coil", result.stdout)
        self.assertIn("reed width: 4.00 in (101.60 mm)", result.stdout)
        self.assertEqual(result.stderr, "")

        document = self.read_log()
        self.assertEqual(document["version"], 1)
        self.assertEqual(document["next_id"], 2)
        self.assertEqual(len(document["entries"]), 1)
        entry = document["entries"][0]
        self.assertEqual(entry["id"], 1)
        self.assertEqual(entry["name"], "Willow Coil")
        self.assertEqual(entry["reed_width_value"], 4.0)
        self.assertEqual(entry["reed_width_unit"], "in")
        self.assertAlmostEqual(entry["reed_width_mm"], 101.6)
        self.assertEqual(entry["sample_rows"], 10)
        self.assertEqual(entry["row_height_before_mm"], 100.0)
        self.assertEqual(entry["row_height_after_mm"], 88.0)
        self.assertTrue(entry["created_at"].endswith("Z"), entry["created_at"])

    def test_second_add_gets_the_next_id_and_list_keeps_ascending_order(self) -> None:
        self.add_valid()
        second = self.cli(
            "add",
            "--name",
            "Bulrush Tray",
            "--reed-width",
            "10",
            "--unit",
            "cm",
            "--sample-rows",
            "8",
            "--row-height-before",
            "80",
            "--row-height-after",
            "72",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Added entry 2: Bulrush Tray", second.stdout)
        self.assertIn("reed width: 10.00 cm (100.00 mm)", second.stdout)

        listing = self.cli("list")
        self.assertEqual(listing.returncode, 0)
        first_pos = listing.stdout.index("Willow Coil")
        second_pos = listing.stdout.index("Bulrush Tray")
        self.assertLess(first_pos, second_pos)
        self.assertIn("8", listing.stdout.split("Bulrush Tray")[1].split("\n")[0])

    def test_ids_are_monotonic_and_never_reused(self) -> None:
        self.add_valid()
        # A hand-edited log that forgot to advance next_id must not reuse id 1.
        document = self.read_log()
        document["next_id"] = 1
        with open(self.log, "w", encoding="utf-8") as stream:
            json.dump(document, stream)

        second = self.cli(
            "add",
            "--name",
            "Cattail Bowl",
            "--reed-width",
            "6",
            "--unit",
            "mm",
            "--sample-rows",
            "4",
            "--row-height-before",
            "40",
            "--row-height-after",
            "34",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("Added entry 2: Cattail Bowl", second.stdout)
        self.assertEqual([e["id"] for e in self.read_log()["entries"]], [1, 2])

    def test_blank_and_whitespace_names_are_rejected(self) -> None:
        self.add_valid()
        with open(self.log, "rb") as stream:
            before = stream.read()

        for blank in ("", "   "):
            with self.subTest(name=repr(blank)):
                result = self.cli(*[blank if part == "Willow Coil" else part for part in VALID_ADD])
                self.assertEqual(result.returncode, 2)
                self.assertIn("name", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assert_log_untouched(before)

    def test_validation_matrix_names_the_flag_and_keeps_the_log(self) -> None:
        self.add_valid()
        with open(self.log, "rb") as stream:
            before = stream.read()

        cases = {
            "--sample-rows": [
                "add", "--name", "X", "--reed-width", "4",
                "--row-height-before", "100", "--row-height-after", "88",
            ],
            "--reed-width": [
                "add", "--name", "X", "--reed-width", "0", "--sample-rows", "10",
                "--row-height-before", "100", "--row-height-after", "88",
            ],
            "--row-height-before": [
                "add", "--name", "X", "--reed-width", "4", "--sample-rows", "10",
                "--row-height-before", "0", "--row-height-after", "88",
            ],
            "--row-height-after": [
                "add", "--name", "X", "--reed-width", "4", "--sample-rows", "10",
                "--row-height-before", "100", "--row-height-after", "-5",
            ],
            "--unit": [
                "add", "--name", "X", "--reed-width", "4", "--unit", "furlong",
                "--sample-rows", "10", "--row-height-before", "100",
                "--row-height-after", "88",
            ],
            "--reed-width numeric": [
                "add", "--name", "X", "--reed-width", "wide", "--sample-rows", "10",
                "--row-height-before", "100", "--row-height-after", "88",
            ],
            "--sample-rows integer": [
                "add", "--name", "X", "--reed-width", "4", "--sample-rows", "10.5",
                "--row-height-before", "100", "--row-height-after", "88",
            ],
            "--name": [
                "add", "--reed-width", "4", "--sample-rows", "10",
                "--row-height-before", "100", "--row-height-after", "88",
            ],
        }
        for flag, argv in cases.items():
            expected = flag.split(" ")[0]
            with self.subTest(flag=flag):
                result = self.cli(*argv)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
                self.assert_log_untouched(before)

    def test_centimetres_are_normalised_to_millimetres(self) -> None:
        result = self.cli(
            "add",
            "--name",
            "Sample",
            "--reed-width",
            "10",
            "--unit",
            "cm",
            "--sample-rows",
            "8",
            "--row-height-before",
            "80",
            "--row-height-after",
            "72",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reed width: 10.00 cm (100.00 mm)", result.stdout)

        entry = self.read_log()["entries"][0]
        self.assertEqual(entry["reed_width_unit"], "cm")
        self.assertAlmostEqual(entry["reed_width_mm"], 100.0)

        listing = self.cli("list")
        self.assertIn("10.00 cm (100.00 mm)", listing.stdout)
        self.assertIn("8", listing.stdout.split("Sample")[1].split("\n")[0])

    def test_unit_defaults_to_inches(self) -> None:
        result = self.cli(
            "add", "--name", "Default Unit", "--reed-width", "0.5",
            "--sample-rows", "5", "--row-height-before", "50",
            "--row-height-after", "45",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reed width: 0.50 in (12.70 mm)", result.stdout)

    def test_add_json_mode_prints_the_stored_entry(self) -> None:
        result = self.cli(*VALID_ADD, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["id"], 1)
        self.assertAlmostEqual(payload["reed_width_mm"], 101.6)

    def test_add_reports_an_unwritable_path(self) -> None:
        missing = os.path.join(self.dir, "no-such-dir", "log.json")
        result = run_cli(*VALID_ADD, "--log", missing)
        self.assertEqual(result.returncode, 1)
        self.assertIn(missing, result.stderr)
        self.assertFalse(os.path.exists(missing))

    def test_unicode_names_round_trip(self) -> None:
        name = "Sjögräs Korg — större"
        result = self.cli(
            "add", "--name", name, "--reed-width", "4", "--sample-rows", "10",
            "--row-height-before", "100", "--row-height-after", "88",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(name, result.stdout)
        self.assertIn(name, self.cli("list").stdout)
        self.assertEqual(self.read_log()["entries"][0]["name"], name)


class ListCommandTests(CliTest):
    def test_empty_log_prompts_with_a_copy_pasteable_example(self) -> None:
        result = self.cli("list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("No entries yet", result.stdout)
        self.assertIn("python basketrystitch.py add", result.stdout)
        self.assertIn("--reed-width 4", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_populated_log_prints_header_and_one_line_per_entry(self) -> None:
        self.add_valid()
        self.cli(
            "add", "--name", "Bulrush Tray", "--reed-width", "10", "--unit", "cm",
            "--sample-rows", "8", "--row-height-before", "80",
            "--row-height-after", "72",
        )
        listing = self.cli("list")
        self.assertEqual(listing.returncode, 0, listing.stderr)
        lines = listing.stdout.splitlines()
        body = [line for line in lines if line.strip() and line.lstrip()[:1].isdigit()]
        self.assertEqual(len(body), 2)
        self.assertIn("NAME", listing.stdout)
        self.assertIn("REED WIDTH", listing.stdout)
        self.assertIn("4.00 in (101.60 mm)", listing.stdout)
        self.assertIn("10.00 cm (100.00 mm)", listing.stdout)
        self.assertIn("12.0%", listing.stdout)
        self.assertIn("10.0%", listing.stdout)
        self.assertIn("100.00", listing.stdout)
        self.assertIn("88.00", listing.stdout)

    def test_corrupt_log_is_reported_and_left_untouched(self) -> None:
        with open(self.log, "w", encoding="utf-8") as stream:
            stream.write('{"version": 1, "entries": [')
        with open(self.log, "rb") as stream:
            before = stream.read()

        result = self.cli("list")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(self.log, result.stderr)
        self.assertIn("JSON", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assert_log_untouched(before)

    def test_wrong_shape_of_log_is_reported(self) -> None:
        with open(self.log, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "next_id": 1, "entries": [{"id": "one"}]}, stream)
        result = self.cli("list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("entries[0]", result.stderr)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read anything")
    def test_unreadable_log_reports_a_permission_problem(self) -> None:
        with open(self.log, "w", encoding="utf-8") as stream:
            json.dump({"version": 1, "next_id": 1, "entries": []}, stream)
        os.chmod(self.log, 0o000)
        self.addCleanup(os.chmod, self.log, 0o600)

        result = self.cli("list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot read", result.stderr)

    def test_list_json_mode_exposes_derived_values(self) -> None:
        self.add_valid()
        result = self.cli("list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["count"], 1)
        entry = payload["entries"][0]
        self.assertAlmostEqual(entry["per_row_after_mm"], 8.8)
        self.assertAlmostEqual(entry["shrinkage_pct"], 12.0)

    def test_list_of_a_thousand_entries_stays_fast(self) -> None:
        entries = [
            basketrystitch.build_entry(
                index, "Sample {}".format(index), 4.0, "in", 10, 100.0, 88.0
            )
            for index in range(1, 1001)
        ]
        with open(self.log, "w", encoding="utf-8") as stream:
            json.dump(
                {"version": 1, "next_id": 1001, "entries": entries}, stream
            )
        start = __import__("time").perf_counter()
        result = self.cli("list")
        elapsed = __import__("time").perf_counter() - start
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(elapsed, 2.0)


class EstimateCommandTests(CliTest):
    def test_target_rows_projects_the_finished_height(self) -> None:
        self.add_valid()
        result = self.cli("estimate", "--id", "1", "--target-rows", "50")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("per-row after: 8.80 mm", result.stdout)
        self.assertIn("shrinkage: 12.0%", result.stdout)
        self.assertIn("projected finished height: 440.00 mm", result.stdout)

    def test_target_height_projects_the_row_count(self) -> None:
        self.add_valid()
        result = self.cli("estimate", "--id", "1", "--target-height", "440")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("projected rows: 50", result.stdout)
        self.assertIn("per-row after: 8.80 mm", result.stdout)
        self.assertIn("shrinkage: 12.0%", result.stdout)

    def test_unknown_id_is_named(self) -> None:
        self.add_valid()
        with open(self.log, "rb") as stream:
            before = stream.read()
        result = self.cli("estimate", "--id", "99", "--target-rows", "10")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no entry with id 99", result.stderr)
        self.assert_log_untouched(before)

    def test_empty_log_asks_for_an_entry_first(self) -> None:
        result = self.cli("estimate", "--id", "1", "--target-rows", "10")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No entries yet", result.stderr)
        self.assertIn("add one first", result.stderr)
        self.assertIn("--row-height-after 88", result.stderr)

    def test_non_numeric_target_rows_names_the_flag(self) -> None:
        self.add_valid()
        result = self.cli("estimate", "--id", "1", "--target-rows", "abc")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--target-rows", result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_both_or_neither_target_is_rejected(self) -> None:
        self.add_valid()
        both = self.cli(
            "estimate", "--id", "1", "--target-rows", "50", "--target-height", "440"
        )
        neither = self.cli("estimate", "--id", "1")
        for result in (both, neither):
            with self.subTest(args=result.args):
                self.assertEqual(result.returncode, 2)
                self.assertIn("exactly one", result.stderr)
                self.assertIn("--target-rows", result.stderr)
                self.assertIn("--target-height", result.stderr)

    def test_non_positive_targets_are_rejected(self) -> None:
        self.add_valid()
        for args in (
            ["--target-rows", "0"],
            ["--target-rows", "-4"],
            ["--target-height", "0"],
        ):
            with self.subTest(args=args):
                result = self.cli("estimate", "--id", "1", *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn(args[0], result.stderr)

    def test_estimate_json_mode(self) -> None:
        self.add_valid()
        result = self.cli("estimate", "--id", "1", "--target-rows", "50", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["projected_finished_height_mm"], 440.0)
        self.assertAlmostEqual(payload["per_row_after_mm"], 8.8)
        self.assertAlmostEqual(payload["shrinkage_pct"], 12.0)

    def test_corrupt_log_is_reported(self) -> None:
        with open(self.log, "w", encoding="utf-8") as stream:
            stream.write("not json at all")
        result = self.cli("estimate", "--id", "1", "--target-rows", "10")
        self.assertEqual(result.returncode, 1)
        self.assertIn(self.log, result.stderr)


class AtomicWriteTests(CliTest):
    def setUp(self) -> None:
        super().setUp()
        self.add_valid()
        with open(self.log, "rb") as stream:
            self.original = stream.read()

    def test_interrupted_save_leaves_the_previous_log_untouched(self) -> None:
        before_files = set(os.listdir(self.dir))
        captured = io.StringIO()
        with mock.patch.object(
            basketrystitch.os, "replace", side_effect=OSError(28, "No space left")
        ), contextlib.redirect_stderr(captured):
            exit_code = basketrystitch.main(
                [
                    "add", "--name", "Interrupted", "--reed-width", "4",
                    "--sample-rows", "10", "--row-height-before", "100",
                    "--row-height-after", "88", "--log", self.log,
                ]
            )
        self.assertEqual(exit_code, 1)
        self.assertIn("cannot write", captured.getvalue())

        with open(self.log, "rb") as stream:
            self.assertEqual(stream.read(), self.original)
        self.assertEqual(self.read_log()["entries"][0]["name"], "Willow Coil")
        self.assertEqual(set(os.listdir(self.dir)), before_files, "no temp file left")

    def test_successful_save_leaves_no_temp_files(self) -> None:
        self.cli(
            "add", "--name", "Second", "--reed-width", "4", "--sample-rows", "10",
            "--row-height-before", "100", "--row-height-after", "88",
        )
        leftovers = [n for n in os.listdir(self.dir) if n.startswith(".basketrystitch-")]
        self.assertEqual(leftovers, [])

    def test_failed_validation_does_not_touch_the_log(self) -> None:
        self.cli(
            "add", "--name", "   ", "--reed-width", "4", "--sample-rows", "10",
            "--row-height-before", "100", "--row-height-after", "88",
        )
        self.assert_log_untouched(self.original)


class ProjectionMathTests(unittest.TestCase):
    """The documented reference case, checked as pure functions (D4)."""

    def setUp(self) -> None:
        self.entry = basketrystitch.build_entry(
            1, "Willow Coil", 4.0, "in", 10, 100.0, 88.0
        )

    def test_per_row_after_is_the_finished_total_over_the_rows(self) -> None:
        self.assertAlmostEqual(basketrystitch.per_row_after_mm(self.entry), 8.8)

    def test_shrinkage_percent(self) -> None:
        self.assertAlmostEqual(basketrystitch.shrinkage_pct(self.entry), 12.0)

    def test_projected_height_is_rows_times_per_row(self) -> None:
        projected = 50 * basketrystitch.per_row_after_mm(self.entry)
        self.assertAlmostEqual(projected, 440.0)

    def test_projected_rows_rounds_to_the_nearest_row(self) -> None:
        projected = round(440 / basketrystitch.per_row_after_mm(self.entry))
        self.assertEqual(projected, 50)

    def test_reed_width_conversion_factors(self) -> None:
        self.assertEqual(basketrystitch.UNIT_TO_MM, {"in": 25.4, "cm": 10.0, "mm": 1.0})
        label = basketrystitch.reed_width_label(self.entry)
        self.assertEqual(label, "4.00 in (101.60 mm)")


class HelpAndCliContractTests(unittest.TestCase):
    def test_help_lists_the_three_commands_and_the_global_log_option(self) -> None:
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        for token in ("add", "list", "estimate", "--log"):
            self.assertIn(token, result.stdout)
        self.assertIn("exit codes", result.stdout)

    def test_subcommand_help_is_usable(self) -> None:
        for command in ("add", "list", "estimate"):
            with self.subTest(command=command):
                result = run_cli(command, "--help")
                self.assertEqual(result.returncode, 0)
                self.assertIn("--log", result.stdout)

    def test_bare_invocation_prints_help_and_exits_zero(self) -> None:
        result = run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)

    def test_version_flag(self) -> None:
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("BasketryStitch", result.stdout)

    def test_log_option_is_accepted_before_and_after_the_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = os.path.join(directory, "nested.json")
            first = run_cli(*VALID_ADD, "--log", log)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = run_cli("--log", log, "list")
            after = run_cli("list", "--log", log)
            self.assertEqual(before.returncode, 0, before.stderr)
            self.assertEqual(before.stdout, after.stdout)
            self.assertIn("Willow Coil", before.stdout)

    def test_default_log_path_is_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(*VALID_ADD, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                os.path.exists(os.path.join(directory, "basketrystitch_log.json"))
            )

    def test_ansi_colour_is_off_when_piped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = os.path.join(directory, "log.json")
            run_cli(*VALID_ADD, "--log", log)
            result = run_cli("list", "--log", log)
            self.assertNotIn("\x1b[", result.stdout)


if __name__ == "__main__":
    unittest.main()
