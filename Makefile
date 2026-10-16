SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# CONFIG overrides the download selection or comparison experiment.
CONFIG ?=
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit dataset selection or experiment YAML instead)))
SETUP = source "$(ROOT).envrc" && export VSLAMLAB_BENCHMARK="$$VIO_DATA_DIR/VSLAM-LAB-Benchmark" VSLAMLAB_EVALUATION="$$VIO_RESULTS_DIR/VSLAM-LAB-Evaluation" PYTHONPATH= &&
ARGS = $(if $(CONFIG),--config "$(CONFIG)",)
RUN = "$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/prepare_datasets.py"

.PHONY: help configure bootstrap prepare test run evaluate
help:
	@printf '%s\n' \
	  'make prepare # bootstrap, download and validate selected datasets' \
	  'make run # run the experiment matrix' \
	  'make evaluate # evaluate saved trajectories and create PNG/PDF reports' \
	  'make test # run all offline tests in Pixi' \
	  'CONFIG=... # choose a dataset selection or experiment YAML' \
	  'RGB_MAX=200 # limit make run to a short smoke test' \
	  'RUN_DIR=... # choose a saved run for make evaluate' \
	  'VIO_DATA_DIR=/path/to/ssd make prepare # choose storage'

configure: $(ROOT).envrc

bootstrap: configure
	@bash "$(ROOT)scripts/bootstrap.sh"

# No dependency on env.sh: shared-default changes must not overwrite local edits.
$(ROOT).envrc:
	@cp -n "$(ROOT)scripts/env.sh" "$@"
	@printf '%s\n' 'Created .envrc; edit machine paths there.'

PREP_ARGS = --config "$(if $(CONFIG),$(CONFIG),$${VIO_DATASET_CONFIG:-$(ROOT)configs/datasets/selected.yaml})"
prepare: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && $(RUN) prepare $(PREP_ARGS)
test: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests/migration" -v
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests" -v
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests/evaluation" -v

$(foreach option,METHOD MODE,$(if $(filter command,$(origin $(option))),$(error $(option) is now selected in experiment Methods)))
run: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/run_catalog.py" \
		$(ARGS) $(if $(RGB_MAX),--rgb-max "$(RGB_MAX)",) $(if $(PLAN),--plan,)

evaluate: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/evaluate_result.py" \
		$(ARGS) $(if $(RUN_DIR),--run-dir "$(RUN_DIR)",) $(if $(EXPERIMENT),--experiment "$(EXPERIMENT)",) $(EVAL_ARGS)
