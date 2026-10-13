SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Preserve optional `make env PYTHON=/path/to/python`; defaults live in .envrc.
export PYTHON
VENV ?= $(ROOT).venv
VIS_VENV := $(ROOT).venv-rerun
# CONFIG overrides the download selection or comparison experiment.
CONFIG ?=
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit dataset selection or experiment YAML instead)))
SETUP = source "$(ROOT).envrc" && export VSLAMLAB_BENCHMARK="$$VIO_DATA_DIR/VSLAM-LAB-Benchmark" VSLAMLAB_EVALUATION="$$VIO_RESULTS_DIR/VSLAM-LAB-Evaluation" PYTHONPATH= &&
ARGS = $(if $(CONFIG),--config "$(CONFIG)",)
RUN = "$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/prepare_datasets.py"

.PHONY: help configure bootstrap env plan prepare validate test run run-research methods evaluate visualize visualize-env
help:
	@printf '%s\n' 'make prepare # bootstrap, download and prepare all four selected recordings' 'make prepare CONFIG=... # prepare the selection from an experiment YAML' 'make plan # estimate storage without downloading recordings' 'make validate # validate the four selected recordings' 'make methods # list VSLAM-LAB catalog' 'make run CONFIG=... # run every Methods variant on every Datasets sequence' 'make run RGB_MAX=200 # short native smoke run' 'make run-research VARIANT=... DATASET=... SEQUENCE=... # one research run with evo provenance' 'make evaluate [RUN_DIR=...] # evo evaluation of a research run' 'make visualize [RUN_DIR=...] # Rerun comparison of a research run' 'make test # offline tests (after bootstrap)' 'VIO_DATA_DIR=/path/to/ssd make prepare # use external storage; .envrc is preserved'

configure: $(ROOT).envrc

bootstrap: configure
	@bash "$(ROOT)scripts/bootstrap.sh"

# No dependency on env.sh: shared-default changes must not overwrite local edits.
$(ROOT).envrc:
	@cp -n "$(ROOT)scripts/env.sh" "$@"
	@printf '%s\n' 'Created .envrc; edit machine paths there.'

env: configure $(VENV)/.installed
$(VENV)/.installed: $(ROOT)requirements.txt | configure
	$(SETUP) "$$PYTHON" -m venv "$(VENV)"
	"$(VENV)/bin/python" -m pip install -r "$(ROOT)requirements.txt"
	@touch "$@"

PREP_ARGS = --config "$(if $(CONFIG),$(CONFIG),$${VIO_DATASET_CONFIG:-$(ROOT)configs/datasets/selected.yaml})"
plan: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && $(RUN) plan $(PREP_ARGS)
prepare: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && $(RUN) prepare $(PREP_ARGS)
validate: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && $(RUN) validate $(PREP_ARGS)
test: env visualize-env
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests/migration" -v
	$(SETUP) cd "$(ROOT)" && "$(VENV)/bin/python" -m unittest discover -s tests -v
	PYTHONPATH= "$(VIS_VENV)/bin/python" -m unittest discover -s "$(ROOT)tests/evaluation" -v

$(foreach option,METHOD MODE,$(if $(filter command,$(origin $(option))),$(error $(option) is now selected in experiment Methods)))
run: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/run_catalog.py" \
		$(ARGS) $(if $(RGB_MAX),--rgb-max "$(RGB_MAX)",) $(if $(PLAN),--plan,)

methods: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab print-baselines

run-research: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab \
		python "$(ROOT)scripts/run_vio.py" $(ARGS) \
		$(if $(VARIANT),--variant "$(VARIANT)",) $(if $(DATASET),--dataset "$(DATASET)",) $(if $(SEQUENCE),--sequence "$(SEQUENCE)",) $(if $(RGB_MAX),--rgb-max "$(RGB_MAX)",)

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
