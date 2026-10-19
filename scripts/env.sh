#!/usr/bin/env bash
# Public defaults. `make configure` copies this file to .envrc once.
# Edit .envrc for your machine; edit this file to change shared defaults.
# .envrc is sourced as shell code: do not load one from an untrusted source.

export ROOT_DIR="${ROOT_DIR:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)}"

# Select an experiment; algorithm parameters remain in the selected YAML.
export VIO_EXPERIMENT_CONFIG="${VIO_EXPERIMENT_CONFIG:-$ROOT_DIR/configs/experiments/report.yaml}"
export VIO_DATASET_CONFIG="${VIO_DATASET_CONFIG:-$ROOT_DIR/configs/experiments/report.yaml}"

# Machine-specific paths, not algorithm parameters.
export VIO_DATA_DIR="${VIO_DATA_DIR:-$HOME/datasets/vio_research}"
# Each run gets a dated subdirectory here; no need to change this path per run.
export VIO_RESULTS_DIR="${VIO_RESULTS_DIR:-$ROOT_DIR/results/vio}"
export VSLAMLAB_BENCHMARK="$VIO_DATA_DIR/VSLAM-LAB-Benchmark"
export VSLAMLAB_EVALUATION="$VIO_RESULTS_DIR/VSLAM-LAB-Evaluation"
export PIXI_BIN="${PIXI_BIN:-$ROOT_DIR/.tools/pixi}"
export PIXI_CACHE_DIR="${PIXI_CACHE_DIR:-$ROOT_DIR/.tools/pixi-cache}"

# Pixi must also be available to the framework's child process.
export PATH="$(dirname "$PIXI_BIN"):$PATH"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
