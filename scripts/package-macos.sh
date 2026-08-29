#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 || ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法：$0 <版本号> [arm64|x86_64]" >&2
    exit 2
fi

version=$1
expected_architecture=${2:-}
if [[ -n $expected_architecture && $expected_architecture != "arm64" && $expected_architecture != "x86_64" ]]; then
    echo "不支持的预期 macOS 架构：$expected_architecture" >&2
    exit 2
fi
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_root=$(cd "$script_dir/.." && pwd)
python_command=${PYTHON:-python3}
venv_dir="$project_root/.venv-macos"
venv_python="$venv_dir/bin/python"
release_dir="$project_root/outputs/release/v$version"
dist_dir="$project_root/dist/macos"
work_dir="$project_root/build/macos-pyinstaller"

if ! "$python_command" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "macOS 构建要求 Python 3.12 或更高版本，可通过 PYTHON=/path/to/python3.12 指定" >&2
    exit 1
fi

project_version=$(
    "$python_command" -c 'import pathlib, re, sys; text = pathlib.Path(sys.argv[1]).read_text(); print(re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"", text).group(1))' \
        "$project_root/pyproject.toml"
)
if [[ $project_version != "$version" ]]; then
    echo "发布版本不一致：参数为 $version，pyproject.toml 为 $project_version" >&2
    exit 1
fi

if [[ -x $venv_python ]] && ! "$venv_python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
    rm -rf "$venv_dir"
fi
if [[ ! -x $venv_python ]]; then
    "$python_command" -m venv "$venv_dir"
fi
"$venv_python" -m pip install --upgrade pip setuptools build twine 'pyinstaller>=6,<7'

rm -rf "$dist_dir" "$work_dir" "$release_dir"
mkdir -p "$release_dir"

PYTHONPATH="$project_root/src" "$venv_python" -m unittest discover -s "$project_root/tests" -q
"$venv_python" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name luna-agent \
    --paths "$project_root/src" \
    --specpath "$work_dir" \
    --workpath "$work_dir" \
    --distpath "$dist_dir" \
    --add-data "$project_root/assets:assets" \
    "$project_root/scripts/launcher.py"

architecture=$("$venv_python" -c 'import platform; print(platform.machine().lower())')
case "$architecture" in
    arm64|aarch64)
        architecture=arm64
        ;;
    x86_64|amd64)
        architecture=x86_64
        ;;
    *)
        echo "不支持的 macOS 架构：$architecture" >&2
        exit 1
        ;;
esac
if [[ -n $expected_architecture && $architecture != "$expected_architecture" ]]; then
    echo "macOS runner 架构不正确：实际为 $architecture，期望为 $expected_architecture" >&2
    exit 1
fi

release_binary="$release_dir/luna-agent-macos-$architecture"
cp "$dist_dir/luna-agent" "$release_binary"
chmod 755 "$release_binary"

binary_version=$($release_binary --version)
if [[ $binary_version != "$version" ]]; then
    echo "生成的 macOS 可执行文件版本不正确：$binary_version，期望：$version" >&2
    exit 1
fi

smoke_root=$(mktemp -d "${TMPDIR:-/private/tmp}/luna-agent-bridge-smoke.XXXXXX")
mkdir -p "$smoke_root/bin"
cp "$release_binary" "$smoke_root/bin/luna-agent"
cleanup_smoke() {
    "$release_binary" --app-root "$smoke_root" broker shutdown --json >/dev/null 2>&1 || true
    rm -rf "$smoke_root"
}
trap cleanup_smoke EXIT
health_response=$($release_binary --app-root "$smoke_root" broker health --json)
if [[ $health_response != '{"status":"ok"}' ]]; then
    echo "macOS Broker 健康检查失败：$health_response" >&2
    exit 1
fi
shutdown_response=$($release_binary --app-root "$smoke_root" broker shutdown --json)
if [[ $shutdown_response != '{"status":"stopping"}' ]]; then
    echo "macOS Broker 关闭检查失败：$shutdown_response" >&2
    exit 1
fi
trap - EXIT
rm -rf "$smoke_root"

echo "macOS 发布产物已生成：$release_binary"
