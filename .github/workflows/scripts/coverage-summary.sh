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
cd "$(dirname "$0")/../../.." || exit 0

pct() { # covered missed
  awk -v c="$1" -v m="$2" 'BEGIN { t = c + m; printf (t == 0 ? "n/a" : "%.1f%%"), 100 * c / t }'
}

echo "| Service | Line | Branch |"
echo "|---|---|---|"

for csv in src/ledger/*/target/site/jacoco/jacoco.csv; do
  [ -f "$csv" ] || continue
  service=$(echo "$csv" | cut -d/ -f3)
  read -r bm bc lm lc <<<"$(awk -F, 'NR > 1 { bm += $6; bc += $7; lm += $8; lc += $9 }
                            END { print bm, bc, lm, lc }' "$csv")"
  echo "| $service | $(pct "$lc" "$lm") | $(pct "$bc" "$bm") |"
done

for xml in src/*/coverage.xml src/*/*/coverage.xml; do
  [ -f "$xml" ] || continue
  service=$(dirname "$xml" | sed 's|^src/||')
  python3 - "$service" "$xml" <<'PY'
import sys, xml.etree.ElementTree as ET
service, path = sys.argv[1], sys.argv[2]
root = ET.parse(path).getroot()
def pct(rate):
    return f"{float(root.get(rate, 0)) * 100:.1f}%"
print(f"| {service} | {pct('line-rate')} | {pct('branch-rate')} |")
PY
done
