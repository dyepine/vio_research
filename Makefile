SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Preserve optional `make env PYTHON=/path/to/python`; defaults live in .envrc.
export PYTHON
VENV ?= $(ROOT).venv
VIS_VENV := $(ROOT).venv-rerun
CONFIG ?= $(ROOT)configs/datasets/prepare.yaml
SETUP = source "$(ROOT).envrc" &&
# Sequence selection and limits live in YAML. Paths may reference .envrc variables.
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit $(CONFIG) instead)))
ARGS = --config "$(CONFIG)"
RUN = "$(VENV)/bin/python" "$(ROOT)scripts/prepare.py"

.PHONY: help configure env plan prepare download convert validate test run evaluate visualize visualize-env
help:
	@printf '%s\n' 'make configure # create .envrc from scripts/env.sh without overwriting it' 'Edit .envrc: machine paths; edit YAML: experiment settings, sequences and limits' 'make plan    # estimate space for active YAML sequences; no dataset downloads' 'make prepare # download, convert and validate active YAML sequences' 'make download / convert / validate # separate stages' 'make test    # offline synthetic tests' 'make run     # ORB-SLAM3 stereo-VI via VSLAM-LAB; settings in experiment YAML' 'make evaluate [RUN_DIR=/path/to/run] # save evo APE/RPE evaluation' 'make visualize [RUN_DIR=/path/to/run] # compare estimate and GT in Rerun' 'make visualize VIS_ARGS="--save /tmp/comparison.rrd" # headless export' 'make plan CONFIG=/path/to/another.yaml # alternative configuration' 'YAML paths can reference variables exported by .envrc'

configure: $(ROOT).envrc

# No dependency on env.sh: shared-default changes must not overwrite local edits.
$(ROOT).envrc:
	@cp -n "$(ROOT)scripts/env.sh" "$@"
	@printf '%s\n' 'Created .envrc; edit machine paths there.'

env: configure $(VENV)/.installed
$(VENV)/.installed: $(ROOT)requirements.txt | configure
	$(SETUP) "$$PYTHON" -m venv "$(VENV)"
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
test: env visualize-env
	$(SETUP) cd "$(ROOT)" && "$(VENV)/bin/python" -m unittest discover -s tests -v
	PYTHONPATH= "$(VIS_VENV)/bin/python" -m unittest discover -s "$(ROOT)tests/evaluation" -v

run: configure
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab \
		python "$(ROOT)scripts/run_grandtour_alb2.py"

visualize-env: $(VIS_VENV)/.installed
$(VIS_VENV)/.installed: $(ROOT)requirements-visualize.txt | configure
	$(SETUP) "$$PYTHON" -m venv "$(VIS_VENV)"
	PYTHONPATH= "$(VIS_VENV)/bin/python" -m pip install -r "$<"
	@touch "$@"

evaluate: visualize-env configure
	$(SETUP) PYTHONPATH= "$(VIS_VENV)/bin/python" "$(ROOT)scripts/evaluate_result.py" \
		$(if $(RUN_DIR),--run-dir "$(RUN_DIR)",) $(EVAL_ARGS)

visualize: visualize-env configure
	$(SETUP) PYTHONPATH= "$(VIS_VENV)/bin/python" "$(ROOT)scripts/visualize_result.py" \
		$(if $(RUN_DIR),--run-dir "$(RUN_DIR)",) $(VIS_ARGS)
