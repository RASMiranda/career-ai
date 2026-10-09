# Runs on YOUR machine (Windows). Pulls the queue, runs the apply step, pushes the result.
# Usage:  .\scripts\local-apply.ps1                 (uses apply.mode from config.yaml)
#         .\scripts\local-apply.ps1 -Mode assisted  (visible browser; you click submit)
#         .\scripts\local-apply.ps1 -DryRun         (fill forms, submit nothing)
param(
  [string]$Data = "$HOME\career-data",
  [ValidateSet("", "assisted", "auto")][string]$Mode = "",
  [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$env:CAREER_DATA = $Data
$env:PYTHONPATH = "$PSScriptRoot\..\src"

git -C $Data pull --ff-only
$args = @("-m", "jobscan.apply", "run")
if ($Mode)  { $args += @("--mode", $Mode) }
if ($DryRun) { $args += "--dry-run" }
python @args
# A failed run must not stop the push: what it recorded (failures included) is what the next
# scan emails to you as "apply by hand".
if ($LASTEXITCODE -ne 0) { Write-Warning "apply run exited with status $LASTEXITCODE; pushing what it recorded" }

python -m jobscan.apply summary | Out-Null
git -C $Data add applications logs reports
if (git -C $Data status --porcelain) {
  git -C $Data commit -m "apply run $(Get-Date -Format s)"
  git -C $Data push
}
