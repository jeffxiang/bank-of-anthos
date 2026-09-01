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
# Prints a markdown table of line/branch coverage per Maven module from the
# jacoco.csv reports produced by `mvn test`.
set -euo pipefail

echo "### Java coverage (JaCoCo)"
echo
echo "| Module | Line % | Branch % |"
echo "|---|---|---|"

shopt -s nullglob
found=0
for csv in */target/site/jacoco/jacoco.csv src/*/*/target/site/jacoco/jacoco.csv src/*/target/site/jacoco/jacoco.csv; do
  found=1
  module="${csv%%/target/*}"
  awk -F, -v module="$module" '
    NR > 1 {
      bm += $6; bc += $7; lm += $8; lc += $9
    }
    END {
      lp = (lm + lc) > 0 ? 100 * lc / (lm + lc) : 0
      bp = (bm + bc) > 0 ? 100 * bc / (bm + bc) : 0
      printf "| %s | %.1f | %.1f |\n", module, lp, bp
    }
  ' "$csv"
done

if [ "$found" -eq 0 ]; then
  echo "| (no jacoco.csv reports found) | - | - |"
fi
