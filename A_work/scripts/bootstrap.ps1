param([string]$Workspace='')
$ErrorActionPreference='Stop'
if (!$Workspace) { $Workspace=(Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path }
$taskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$upstream=Join-Path $Workspace 'keyword-transformer'
$revision='237e4097afd4f6851e0b82f0a8d65c2dfe8eae30'
if (!(Test-Path -LiteralPath $upstream)) {
    git clone --no-checkout https://github.com/ARM-software/keyword-transformer.git $upstream
    if ($LASTEXITCODE) { throw 'Upstream clone failed' }
    git -C $upstream checkout --detach $revision
    if ($LASTEXITCODE) { throw 'Pinned checkout failed' }
}
$head=(git -C $upstream rev-parse HEAD).Trim()
if ($head -ne $revision) { throw "Upstream revision differs: $head. Preserve it and prepare a separate pinned checkout." }
uv python install 3.8
if ($LASTEXITCODE) { throw 'Python install failed' }
$envPath=Join-Path $Workspace '.venv-a'
if (!(Test-Path -LiteralPath $envPath)) {
    uv venv --python 3.8 $envPath
    if ($LASTEXITCODE) { throw 'venv creation failed' }
}
$python=Join-Path $envPath 'Scripts\python.exe'
uv pip sync --python $python (Join-Path $taskRoot 'requirements-lock.txt') --index-url https://pypi.org/simple
if ($LASTEXITCODE) { throw 'Dependency setup failed' }
Write-Output "Python: $python"
Write-Output "Upstream: $upstream"
