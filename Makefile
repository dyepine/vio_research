SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
VENV ?= $(ROOT).venv
CONFIG ?= $(ROOT)configs/datasets/prepare.yaml
SETUP = source "$(ROOT).envrc" &&
# Sequence selection and limits live in YAML. Paths may reference .envrc variables.
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit $(CONFIG) instead)))
ARGS = --config "$(CONFIG)"
RUN = "$(VENV)/bin/python" "$(ROOT)scripts/prepare.py"

.PHONY: help configure env plan prepare download convert validate test run
help:
	@printf '%s\n' 'make configure # create .envrc from scripts/env.sh without overwriting it' 'Edit .envrc: machine paths; edit YAML: experiment settings, sequences and limits' 'make plan    # estimate space for active YAML sequences; no dataset downloads' 'make prepare # download, convert and validate active YAML sequences' 'make download / convert / validate # separate stages' 'make test    # offline synthetic tests' 'make run     # ORB-SLAM3 stereo-VI via VSLAM-LAB; settings in experiment YAML' 'make plan CONFIG=/path/to/another.yaml # alternative configuration' 'YAML paths can reference variables exported by .envrc'

configure: $(ROOT).envrc

# No dependency on env.sh: shared-default changes must not overwrite local edits.
$(ROOT).envrc:
	@cp -n "$(ROOT)scripts/env.sh" "$@"
	@printf '%s\n' 'Created .envrc; edit machine paths there.'

env: configure $(VENV)/.installed
$(VENV)/.installed: $(ROOT)requirements.txt
	$(PYTHON) -m venv "$(VENV)"
	"$(VENV)/bin/python" -m pip install -r "$(ROOT)requirements.txt"
	@touch "$@"

plan: env
	$(SETUP) $(RUN) plan $(ARGS)
prepare: env
	$(SETUP) $(RUN) prepare $(ARGS)
download: env
	$(SETUP) $(RUN) download $(ARGS)
convert: env
	$(SETUP) $(RUN) convert $(ARGS)
validate: env
	$(SETUP) $(RUN) validate $(ARGS)
test: env
	$(SETUP) cd "$(ROOT)" && "$(VENV)/bin/python" -m unittest discover -s tests -v

run: configure
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab \
		python "$(ROOT)scripts/run_grandtour_alb2.py"
