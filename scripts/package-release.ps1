[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $scriptRoot "..")).Path
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pyprojectPath = Join-Path $projectRoot "pyproject.toml"
$releaseRoot = Join-Path $projectRoot "outputs\release"
$releaseDir = Join-Path $releaseRoot "v$Version"

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $pythonPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python 命令失败，退出码：$LASTEXITCODE，参数：$($Arguments -join ' ')"
    }
}

if (-not (Test-Path -LiteralPath $pyprojectPath -PathType Leaf)) {
    throw "未找到 pyproject.toml：$pyprojectPath"
}

$pyprojectText = Get-Content -Raw -LiteralPath $pyprojectPath
$versionMatch = [regex]::Match($pyprojectText, '(?m)^version\s*=\s*"([^"]+)"')
if (-not $versionMatch.Success) {
    throw "无法从 pyproject.toml 读取项目版本"
}
if ($versionMatch.Groups[1].Value -ne $Version) {
    throw "发布版本不一致：参数为 $Version，pyproject.toml 为 $($versionMatch.Groups[1].Value)"
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    $systemPython = Get-Command python -ErrorAction Stop | Select-Object -First 1
    & $systemPython.Source -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "创建虚拟环境失败，退出码：$LASTEXITCODE"
    }
}

Invoke-Python @(
    "-m",
    "pip",
    "install",
    "--upgrade",
    "pip",
    "setuptools",
    "build",
    "twine",
    "pyinstaller>=6,<7"
)
$env:PYTHONPATH = Join-Path $projectRoot "src"

$cleanPaths = @(
    (Join-Path $projectRoot "build"),
    (Join-Path $projectRoot "dist"),
    $releaseDir
)
foreach ($cleanPath in $cleanPaths) {
    if (Test-Path -LiteralPath $cleanPath) {
        Remove-Item -LiteralPath $cleanPath -Recurse -Force
    }
}
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

# Equivalent commands: python -m unittest discover -s tests -q
Invoke-Python @("-m", "unittest", "discover", "-s", "tests", "-q")
# Equivalent command: python -m build --outdir <release-dir>
Invoke-Python @("-m", "build", "--outdir", $releaseDir)

$assetsDir = Join-Path $projectRoot "assets"
$launcherPath = Join-Path $projectRoot "scripts\launcher.py"
$pyinstallerBuildDir = Join-Path $projectRoot "build\pyinstaller"
Invoke-Python @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name",
    "luna-agent",
    "--paths",
    (Join-Path $projectRoot "src"),
    "--specpath",
    $pyinstallerBuildDir,
    "--workpath",
    $pyinstallerBuildDir,
    "--distpath",
    (Join-Path $projectRoot "dist"),
    "--add-data",
    "$assetsDir;assets",
    $launcherPath
)

$builtExe = Join-Path $projectRoot "dist\luna-agent.exe"
$releaseExe = Join-Path $releaseDir "luna-agent.exe"
if (-not (Test-Path -LiteralPath $builtExe -PathType Leaf)) {
    throw "PyInstaller 未生成可执行文件：$builtExe"
}
Copy-Item -LiteralPath $builtExe -Destination $releaseExe -Force
$exeVersion = (& $releaseExe --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $exeVersion -ne $Version) {
    throw "生成的 luna-agent.exe 版本不正确：$exeVersion，期望：$Version"
}

$pluginDir = Join-Path $projectRoot "plugins\luna-agent-bridge"
$pluginManifestPath = Join-Path $pluginDir ".codex-plugin\plugin.json"
$skillRoot = Join-Path $pluginDir "skills"
$skillDir = Join-Path $skillRoot "luna-agent-bridge"
if (-not (Test-Path -LiteralPath $pluginManifestPath -PathType Leaf)) {
    throw "缺少插件清单：$pluginManifestPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $skillDir "SKILL.md") -PathType Leaf)) {
    throw "缺少插件 Skill：$skillDir\SKILL.md"
}
if (-not (Test-Path -LiteralPath (Join-Path $skillDir "agents\openai.yaml") -PathType Leaf)) {
    throw "缺少插件 Agent 元数据：$skillDir\agents\openai.yaml"
}
$pluginManifest = Get-Content -Raw -LiteralPath $pluginManifestPath | ConvertFrom-Json
if ($pluginManifest.name -ne "luna-agent-bridge" -or $pluginManifest.version -ne $Version) {
    throw "插件清单版本或名称不正确"
}
if ($pluginManifest.skills -ne "./skills/") {
    throw "插件清单 skills 路径不正确：$($pluginManifest.skills)"
}

$pluginZip = Join-Path $releaseDir "luna-agent-bridge-plugin-$Version.zip"
$skillZip = Join-Path $releaseDir "luna-agent-bridge-skill-$Version.zip"
$archiveScript = @'
import sys
import zipfile
from pathlib import Path


def archive(source_root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive_file.write(path, path.relative_to(source_root).as_posix())


archive(Path(sys.argv[1]), Path(sys.argv[2]))
archive(Path(sys.argv[3]), Path(sys.argv[4]))
'@
Invoke-Python @("-c", $archiveScript, $pluginDir, $pluginZip, $skillRoot, $skillZip)

$validatorPath = Join-Path $env:USERPROFILE ".codex\skills\.system\plugin-creator\scripts\validate_plugin.py"
if (Test-Path -LiteralPath $validatorPath -PathType Leaf) {
    Invoke-Python @($validatorPath, $pluginDir)
}

$wheelFiles = @(Get-ChildItem -LiteralPath $releaseDir -Filter "luna_agent_bridge-$Version-*.whl" -File)
$sdistFiles = @(Get-ChildItem -LiteralPath $releaseDir -Filter "luna_agent_bridge-$Version.tar.gz" -File)
if ($wheelFiles.Count -ne 1 -or $sdistFiles.Count -ne 1) {
    throw "Python 发布文件数量不正确：wheel=$($wheelFiles.Count)，sdist=$($sdistFiles.Count)"
}
# Equivalent command: python -m twine check <wheel> <sdist>
Invoke-Python @("-m", "twine", "check", $wheelFiles[0].FullName, $sdistFiles[0].FullName)

$releaseFiles = @(
    $releaseExe,
    $wheelFiles[0].FullName,
    $sdistFiles[0].FullName,
    $pluginZip,
    $skillZip
)
$checksumPath = Join-Path $releaseDir "SHA256SUMS.txt"
$checksumLines = foreach ($releaseFile in ($releaseFiles | Sort-Object)) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $releaseFile).Hash.ToUpperInvariant()
    "$hash  $([System.IO.Path]::GetFileName($releaseFile))"
}
$checksumLines | Set-Content -LiteralPath $checksumPath -Encoding ascii

$expectedFiles = @($releaseFiles) + $checksumPath
foreach ($expectedFile in $expectedFiles) {
    if (-not (Test-Path -LiteralPath $expectedFile -PathType Leaf)) {
        throw "缺少发布文件：$expectedFile"
    }
}

Write-Host "发布产物已生成：$releaseDir"
Get-ChildItem -LiteralPath $releaseDir -File | Sort-Object Name | Select-Object Name, Length
