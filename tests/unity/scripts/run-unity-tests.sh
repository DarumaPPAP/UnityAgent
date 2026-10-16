#!/usr/bin/env bash
# Arguments and exit codes are identical to tests/unity/verify/unity_ci.py.
set -euo pipefail
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${UNITY_CI_PYTHON:-python3}" "$script_directory/../verify/unity_ci.py" "$@"
