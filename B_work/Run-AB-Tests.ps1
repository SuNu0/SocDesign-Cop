param(
    [string]$AWork='',
    [string]$Data='',
    [int]$Layer=0,
    [switch]$AllLayers,
    [switch]$Quick,
    [ValidateRange(1,4)][int]$Workers=3,
    [string]$Python='',
    [string]$Iverilog='',
    [string]$Vvp=''
)
$ErrorActionPreference='Stop'
if ($AllLayers -and $PSBoundParameters.ContainsKey('Layer')) { throw '-Layer and -AllLayers are mutually exclusive.' }
if ($Layer -lt 0 -or $Layer -gt 11) { throw '-Layer must be 0..11.' }
function Resolve-ABTool([string]$Requested,[string]$Name,[string]$Fallback) {
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) { return (Resolve-Path -LiteralPath $Requested).Path }
        $found=Get-Command $Requested -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.Source }
        throw "Tool not found: $Requested"
    }
    $found=Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.Source }
    if (Test-Path -LiteralPath $Fallback -PathType Leaf) { return $Fallback }
    throw "Tool not found: $Name. Specify -Python, -Iverilog or -Vvp."
}
$Python=Resolve-ABTool $Python 'python' 'D:\Software\Python313\python.exe'
$Iverilog=Resolve-ABTool $Iverilog 'iverilog' 'D:\Software\iverilog\bin\iverilog.exe'
$Vvp=Resolve-ABTool $Vvp 'vvp' (Join-Path (Split-Path -Parent $Iverilog) 'vvp.exe')
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts\run_ab_regression.py'),'--iverilog',$Iverilog,'--vvp',$Vvp,'--workers',$Workers)
if ($AWork) { $arguments+=@('--a-work',(Resolve-Path -LiteralPath $AWork).Path) }
if ($Data) { $arguments+=@('--data',(Resolve-Path -LiteralPath $Data).Path) }
if ($AllLayers) { $arguments+='--all-layers' } else { $arguments+=@('--layer',$Layer) }
if ($Quick) { $arguments+='--quick' }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'AB regression failed. See reports/ab_regression.' }
