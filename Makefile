SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
VENV ?= $(ROOT).venv
CONFIG ?= $(or $(wildcard $(ROOT)configs/datasets/prepare.local.yaml),$(ROOT)configs/datasets/prepare.yaml)
# Dataset settings live only in YAML. Reject obsolete explicit overrides.
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit $(CONFIG) instead)))
ARGS = --config "$(CONFIG)"
RUN = "$(VENV)/bin/python" "$(ROOT)scripts/prepare.py"

.PHONY: help env plan prepare download convert validate test run
help:
	@printf '%s\n' 'Edit configs/datasets/prepare.yaml: data_dir, sequences (true/false), storage limits' 'make plan    # estimate space for active YAML sequences; no dataset downloads' 'make prepare # download, convert and validate active YAML sequences' 'make download / convert / validate # separate stages' 'make test    # offline synthetic tests' 'make run     # ORB-SLAM3 stereo-VI via VSLAM-LAB; settings in experiment YAML' 'make plan CONFIG=/path/to/another.yaml # alternative configuration' 'Dataset directory, sequences and storage limits are read only from YAML'

env: $(VENV)/.installed
$(VENV)/.installed: $(ROOT)requirements.txt
	$(PYTHON) -m venv "$(VENV)"
	"$(VENV)/bin/python" -m pip install -r "$(ROOT)requirements.txt"
	@touch "$@"

plan: env
	$(RUN) plan $(ARGS)
prepare: env
	$(RUN) prepare $(ARGS)
download: env
	$(RUN) download $(ARGS)
convert: env
	$(RUN) convert $(ARGS)
validate: env
	$(RUN) validate $(ARGS)
test: env
	cd "$(ROOT)" && "$(VENV)/bin/python" -m unittest discover -s tests -v

# Pixi must also be on PATH for the launcher's child ORB-SLAM3 process.
# Reuse the installation cache unless the caller selected a different one.
run:
	cd "$(ROOT)external/VSLAM-LAB" && \
		PATH="$(ROOT).tools:$$PATH" \
		PIXI_CACHE_DIR="$${PIXI_CACHE_DIR:-$(ROOT).tools/pixi-cache}" \
		OMP_NUM_THREADS="$${OMP_NUM_THREADS:-2}" \
		OPENBLAS_NUM_THREADS="$${OPENBLAS_NUM_THREADS:-1}" \
		"$(ROOT).tools/pixi" run --frozen -e vslamlab \
		python "$(ROOT)scripts/run_grandtour_alb2.py"
