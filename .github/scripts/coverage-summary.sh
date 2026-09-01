#!/usr/bin/env bash
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
#
# Prints a markdown table of line/branch coverage for every service that
# produced a report. Report-only: never fails the build.

set -uo pipefail
cd "$(dirname "$0")/../.."

echo "## Unit test coverage"
echo
echo "| Service | Line | Branch |"
echo "|---|---|---|"

for csv in src/ledger/*/target/site/jacoco/jacoco.csv src/ledgermonolith/target/site/jacoco/jacoco.csv; do
  [ -f "$csv" ] || continue
  service=$(echo "$csv" | cut -d/ -f2-3 | sed 's|/target.*||')
  awk -F, -v service="$service" '
    NR > 1 {
      bm += $4; bc += $5; lm += $6; lc += $7
    }
    END {
      line = (lm + lc) ? 100 * lc / (lm + lc) : 0
      branch = (bm + bc) ? 100 * bc / (bm + bc) : 0
      printf "| %s | %.1f%% | %.1f%% |\n", service, line, branch
    }' "$csv"
done

for xml in src/accounts/*/coverage.xml src/frontend/coverage.xml; do
  [ -f "$xml" ] || continue
  service=$(dirname "$xml" | sed 's|^src/||')
  python3 - "$xml" "$service" <<'PY'
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
line = float(root.get("line-rate", 0)) * 100
branch = float(root.get("branch-rate", 0)) * 100
print(f"| {sys.argv[2]} | {line:.1f}% | {branch:.1f}% |")
PY
done
