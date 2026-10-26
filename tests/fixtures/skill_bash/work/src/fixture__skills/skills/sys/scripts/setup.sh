#!/usr/bin/env bash
set -euo pipefail
# rm -rf / would be bad
crontab mycron.txt
eval "$CMD"
rm -rf build
