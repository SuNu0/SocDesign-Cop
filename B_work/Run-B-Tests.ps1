param(
    [switch]$Quick,
    [switch]$FullLayers,
    [string]$Python='',
    [string]$Iverilog='',
    [string]$Vvp=''
)
$ErrorActionPreference='Stop'
if ($Quick -and $FullLayers) { throw '-Quick and -FullLayers are mutually exclusive.' }
function Resolve-BTool([string]$Requested,[string]$Name,[string]$Fallback) {
    if ($Requested) {
        if (Test-Path -LiteralPath $Requested -PathType Leaf) { return (Resolve-Path -LiteralPath $Requested).Path }
        $found=Get-Command $Requested -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.Source }
        throw "Tool not found: $Requested"
    }
    $found=Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.Source }
    if (Test-Path -LiteralPath $Fallback -PathType Leaf) { return $Fallback }
    throw "Tool not found: $Name. Set the corresponding -Python, -Iverilog or -Vvp parameter."
}
$Python=Resolve-BTool $Python 'python' 'D:\Software\Python313\python.exe'
$Iverilog=Resolve-BTool $Iverilog 'iverilog' 'D:\Software\iverilog\bin\iverilog.exe'
$Vvp=Resolve-BTool $Vvp 'vvp' (Join-Path (Split-Path -Parent $Iverilog) 'vvp.exe')
$arguments=@('-B',(Join-Path $PSScriptRoot 'scripts\run_b_regression.py'),'--iverilog',$Iverilog,'--vvp',$Vvp)
if ($Quick) { $arguments+='--quick' }
if ($FullLayers) { $arguments+='--full-layers' }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'B regression failed. See reports/b_regression.' }
