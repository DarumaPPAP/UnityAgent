# UnityAgentの既存Fixtureから独立Projectを生成し、実Editor E2Eを対話的に実行する。
[CmdletBinding()]
param(
    [string]$EditorPath = 'C:\Program Files\Unity\Hub\Editor\6000.3.12f1\Editor\Unity.exe',
    [string]$ExpectedSha,
    [switch]$PlanOnly
)
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'run.py'
$args = @($runner, '--editor', $EditorPath)
if ($ExpectedSha) { $args += @('--expected-sha', $ExpectedSha) }
if ($PlanOnly) { $args += '--plan-only' }
& py -3.12 @args
exit $LASTEXITCODE
