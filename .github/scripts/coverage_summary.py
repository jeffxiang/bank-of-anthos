#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Print a markdown coverage summary for every service that produced a report.

Report-only: missing reports are listed as "no report" and never cause a
non-zero exit status.
"""

import csv
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]

JACOCO_CSV = {
    "ledgerwriter": "src/ledger/ledgerwriter/target/site/jacoco/jacoco.csv",
    "balancereader": "src/ledger/balancereader/target/site/jacoco/jacoco.csv",
    "transactionhistory": "src/ledger/transactionhistory/target/site/jacoco/jacoco.csv",
}

COBERTURA_XML = {
    "frontend": "src/frontend/coverage.xml",
    "userservice": "src/accounts/userservice/coverage.xml",
    "contacts": "src/accounts/contacts/coverage.xml",
    "ui-angular": "src/ui-angular/coverage/ui-angular/cobertura-coverage.xml",
}


def _pct(covered, total):
    if not total:
        return None
    return 100.0 * covered / total


def jacoco_totals(path):
    lines_missed = lines_covered = branches_missed = branches_covered = 0
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            lines_missed += int(row["LINE_MISSED"])
            lines_covered += int(row["LINE_COVERED"])
            branches_missed += int(row["BRANCH_MISSED"])
            branches_covered += int(row["BRANCH_COVERED"])
    return (
        _pct(lines_covered, lines_covered + lines_missed),
        _pct(branches_covered, branches_covered + branches_missed),
    )


def cobertura_totals(path):
    root = ET.parse(path).getroot()
    line_rate = root.get("line-rate")
    branch_rate = root.get("branch-rate")
    return (
        100.0 * float(line_rate) if line_rate is not None else None,
        100.0 * float(branch_rate) if branch_rate is not None else None,
    )


def fmt(value):
    return "n/a" if value is None else f"{value:.1f}%"


def main():
    rows = []
    for service, rel in sorted(JACOCO_CSV.items()) + sorted(COBERTURA_XML.items()):
        path = ROOT / rel
        if not path.exists():
            rows.append((service, "no report", "no report"))
            continue
        try:
            line, branch = (
                jacoco_totals(path) if path.suffix == ".csv" else cobertura_totals(path)
            )
        except (ET.ParseError, KeyError, ValueError) as err:
            rows.append((service, f"unreadable ({err})", ""))
            continue
        rows.append((service, fmt(line), fmt(branch)))

    print("## Coverage (report-only)\n")
    print("| Service | Line | Branch |")
    print("| --- | --- | --- |")
    for service, line, branch in rows:
        print(f"| {service} | {line} | {branch} |")
    print("\nThis report never fails the build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
