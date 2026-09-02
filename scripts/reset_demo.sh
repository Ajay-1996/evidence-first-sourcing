#!/bin/bash
# Reset the demo to a clean pre-ingestion state (keeps RFx + vendor files)
cd "$(dirname "$0")/.."
rm -f data/comparison.json data/decisions.json data/decision_log.json data/traces.json data/evidence/*.json 2>/dev/null
echo "Demo reset: no ingestions, no decisions. RFx + vendor artifacts intact."
