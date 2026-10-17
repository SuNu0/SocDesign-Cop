param(
    [Parameter(Mandatory=$true)][string]$Vivado,
    [string]$Vectors = '',
    [string]$Build = ''
)
$ErrorActionPreference='Stop'
$taskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (!$Vectors) { $Vectors = Join-Path $taskRoot 'build\synthetic_vectors' }
if (!$Build) { $Build = Join-Path $taskRoot ('build\xsim_' + (Get-Date -Format 'yyyyMMdd_HHmmss')) }
$vectorsAbs = (Resolve-Path $Vectors).Path
if (Test-Path -LiteralPath $Build) { throw "Build directory already exists. Choose a new path: $Build" }
New-Item -ItemType Directory -Path $Build | Out-Null
$buildAbs=(Resolve-Path $Build).Path
Push-Location $taskRoot
try {
    & $Vivado -mode batch -source (Join-Path $PSScriptRoot 'run_xsim.tcl') -log (Join-Path $buildAbs 'vivado.log') -journal (Join-Path $buildAbs 'vivado.jou') -tclargs $vectorsAbs $buildAbs
    if ($LASTEXITCODE -ne 0) { throw "Vivado process failed: $LASTEXITCODE" }
    $simLog=Join-Path $buildAbs 'a_compute.sim\sim_1\behav\xsim\simulate.log'
    $log=Get-Content -LiteralPath $simLog -Raw
    if ($log -notmatch 'ALL_A_COMPUTE_TESTS_PASSED' -or $log -match '(?im)(Fatal:|Error:|\$fatal|WATCHDOG phase=)') {
        throw "Functional pass gate failed. Read $simLog"
    }
    Write-Output "A_XSIM_REGRESSION_PASSED: $simLog"
} finally { Pop-Location }
