#!/usr/bin/env bash
# Public defaults. `make configure` copies this file to .envrc once.
# Edit .envrc for your machine; edit this file to change shared defaults.
# .envrc is sourced as shell code: do not load one from an untrusted source.

export ROOT_DIR="${ROOT_DIR:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)}"

# Machine-specific paths, not algorithm parameters.
export VIO_DATA_DIR="${VIO_DATA_DIR:-$HOME/datasets/vio_research}"
export VIO_RESULTS_DIR="${VIO_RESULTS_DIR:-$ROOT_DIR/results/grandtour-alb2-run-01}"
export PIXI_BIN="${PIXI_BIN:-$ROOT_DIR/.tools/pixi}"
export PIXI_CACHE_DIR="${PIXI_CACHE_DIR:-$ROOT_DIR/.tools/pixi-cache}"

# Pixi must also be available to the framework's child process.
export PATH="$(dirname "$PIXI_BIN"):$PATH"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
