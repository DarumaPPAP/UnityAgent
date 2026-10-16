#!/usr/bin/env bash
set -euo pipefail

install_root="${1:-${HOME}/.local/lib/unity-artist/Beta}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
project="${repo_root}/cli/artist/UnityArtist.Cli.csproj"

dotnet publish "${project}" --configuration Release --self-contained false --output "${install_root}"
printf 'Installed unity-artist to %s\n' "${install_root}"
printf 'Add that directory to PATH, then verify with: unity-artist version --format json --non-interactive\n'
