#!/usr/bin/env bash
# Minimal Linux x86_64 bootstrap; environments and methods are managed by Pixi/VSLAM-LAB.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "${VIO_ENV_FILE:-$task_root/.envrc}"
task_lab="$task_root/external/VSLAM-LAB"
# Git's submodule entry is the single source of the framework revision.
task_revision=$(git -C "$task_root" rev-parse :external/VSLAM-LAB)
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'Supported bootstrap platform: Linux x86_64.' >&2
    exit 1
fi
if [[ ! -f "$task_lab/.git" && ! -d "$task_lab/.git" ]]; then
    git -C "$task_root" submodule update --init -- external/VSLAM-LAB
fi
if [[ $(git -C "$task_lab" rev-parse HEAD) != "$task_revision" ]]; then
    echo "Unexpected VSLAM-LAB revision; expected $task_revision. Checkout preserved." >&2
    exit 1
fi
if [[ ! -x "$PIXI_BIN" ]]; then
    mkdir -p -- "$(dirname -- "$PIXI_BIN")"
    task_tmp=$(mktemp -d)
    trap 'rm -rf -- "$task_tmp"' EXIT
    curl --fail --location --retry 5 --connect-timeout 30 \
        https://github.com/prefix-dev/pixi/releases/download/v0.81.0/pixi-x86_64-unknown-linux-musl.tar.gz \
        -o "$task_tmp/pixi.tar.gz"
    (cd "$task_tmp" && echo '7aa3ec39aecceff9062fa2ed4d42cbaa0bdc25ddea727d048e061cf188d434f6  pixi.tar.gz' | sha256sum -c -)
    tar -xzf "$task_tmp/pixi.tar.gz" -C "$task_tmp" pixi
    install -m 755 "$task_tmp/pixi" "$PIXI_BIN"
fi
cd "$task_lab"
PYTHONPATH= "$PIXI_BIN" install --frozen -e vslamlab -e ros1
