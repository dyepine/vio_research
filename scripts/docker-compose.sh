#!/usr/bin/env bash
# Read local shell settings on the host; pass only supported values to Compose.
set -euo pipefail
task_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$task_root"
export ROOT_DIR="$task_root"
source "${VIO_ENV_FILE:-$task_root/.envrc}"
# Older .envrc files may lack newer shared defaults.
source "$task_root/scripts/env.sh"
VIO_DATA_DIR=$(realpath -m -- "$VIO_DATA_DIR")
VIO_RESULTS_DIR=$(realpath -m -- "$VIO_RESULTS_DIR")
export VIO_DATA_DIR VIO_RESULTS_DIR
container_config() {
    local host_path
    host_path=$(realpath -m -- "$1")
    if [[ $host_path != "$task_root/"* ]]; then
        printf 'Docker config must be inside the checkout: %s\n' "$host_path" >&2
        return 1
    fi
    printf '/workspace/%s' "${host_path#"$task_root/"}"
}
container_result() {
    local host_path
    host_path=$(realpath -m -- "$1")
    case "$host_path" in
        /results|/results/*) printf '%s' "$host_path" ;;
        "$VIO_RESULTS_DIR") printf '/results' ;;
        "$VIO_RESULTS_DIR/"*) printf '/results/%s' "${host_path#"$VIO_RESULTS_DIR/"}" ;;
        *) printf 'Run must be inside VIO_RESULTS_DIR or /results: %s\n' "$host_path" >&2; return 1 ;;
    esac
}
VIO_CONTAINER_EXPERIMENT_CONFIG=$(container_config "$VIO_EXPERIMENT_CONFIG")
VIO_CONTAINER_DATASET_CONFIG=$(container_config "$VIO_DATASET_CONFIG")
export VIO_CONTAINER_EXPERIMENT_CONFIG VIO_CONTAINER_DATASET_CONFIG
compose_args=()
for argument in "$@"; do
    case "$argument" in
        CONFIG=*) argument="CONFIG=$(container_config "${argument#CONFIG=}")" ;;
        RUN_DIR=*|EXPERIMENT=*) argument="${argument%%=*}=$(container_result "${argument#*=}")" ;;
    esac
    compose_args+=("$argument")
done
if ! docker compose version >/dev/null 2>&1; then
    printf 'Docker with Compose is required; check docker compose version.\n' >&2
    exit 1
fi
exec docker compose "${compose_args[@]}"
