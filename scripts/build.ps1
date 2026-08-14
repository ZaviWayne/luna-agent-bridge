$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptRoot "..")
$venvPath = Join-Path $projectRoot ".venv"
$pythonPath = Join-Path $venvPath "Scripts\python.exe"
$deliveryDir = [System.IO.Path]::GetFullPath((Join-Path $projectRoot "..\..\outputs\luna-agent-bridge"))

if (-not (Test-Path $pythonPath)) {
    python -m venv $venvPath
}
& $pythonPath -m pip install --upgrade pip setuptools
& $pythonPath -m pip install "pyinstaller>=6,<7"
& $pythonPath -m PyInstaller --noconfirm --clean --onefile --name luna-agent --paths (Join-Path $projectRoot "src") --add-data "$(Join-Path $projectRoot 'assets');assets" (Join-Path $projectRoot "scripts\launcher.py")

New-Item -ItemType Directory -Force $deliveryDir | Out-Null
$builtExe = Join-Path $projectRoot "dist\luna-agent.exe"
if (-not (Test-Path $builtExe)) {
    throw "PyInstaller 未生成可执行文件"
}
Copy-Item -Force $builtExe (Join-Path $deliveryDir "luna-agent.exe")
& (Join-Path $deliveryDir "luna-agent.exe") --version
if ($LASTEXITCODE -ne 0) {
    throw "生成的 luna-agent.exe 无法执行 --version"
}
