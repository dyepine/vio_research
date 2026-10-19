SHELL := /bin/bash
.DEFAULT_GOAL := help
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# CONFIG overrides the download selection or comparison experiment.
CONFIG ?=
ENV_FILE ?= $(if $(VIO_ENV_FILE),$(VIO_ENV_FILE),$(ROOT).envrc)
$(foreach option,DATA_DIR SEQUENCES MAX_DATA_GB RESERVE_GB,$(if $(filter command,$(origin $(option))),$(error $(option) is no longer supported; edit dataset selection or experiment YAML instead)))
$(foreach option,METHOD MODE,$(if $(filter command,$(origin $(option))),$(error $(option) is now selected in experiment Methods)))
SETUP = source "$(ENV_FILE)" && export VSLAMLAB_BENCHMARK="$$VIO_DATA_DIR/VSLAM-LAB-Benchmark" VSLAMLAB_EVALUATION="$$VIO_RESULTS_DIR/VSLAM-LAB-Evaluation" PYTHONPATH= &&
ARGS = $(if $(CONFIG),--config "$(CONFIG)",)
RUN = "$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/prepare_datasets.py"

.PHONY: help configure bootstrap prepare test run evaluate
help:
	@printf '%s\n' \
	  'make configure # create .envrc; edit storage paths before preparation' \
	  'make build # build Docker image with all system dependencies' \
	  'make prepare # download and prepare selected datasets' \
	  'make run # run the experiment matrix in Docker' \
	  'make evaluate EVAL_ARGS=--saved-protocol # evaluate the latest run with evo' \
	  'make test # run offline tests in Docker' \
	  'make artifacts # verify saved report metrics without downloading data' \
	  'make config # show resolved Docker paths and mounts' \
	  'make shell # open a container shell' \
	  'CONFIG=configs/experiments/sqrtvins.yaml # select another experiment' \
	  'RGB_MAX=200 JOBS=1 # short run; methods run sequentially' \
	  'RUN_DIR=... # evaluate a specific run (host or /results path)' \
	  'VIO_NATIVE=1 # use an existing native toolchain instead of Docker'

configure: $(ENV_FILE)

# No dependency on env.sh: shared-default changes must not overwrite local edits.
$(ROOT).envrc:
	@cp -n "$(ROOT)scripts/env.sh" "$@"
	@printf '%s\n' 'Created .envrc; edit machine paths there.'

# Public targets use Docker; the image selects native execution explicitly.
ifeq ($(VIO_NATIVE),1)

bootstrap: configure
	@VIO_ENV_FILE="$(ENV_FILE)" bash "$(ROOT)scripts/bootstrap.sh"

PREP_ARGS = --config "$(if $(CONFIG),$(CONFIG),$${VIO_DATASET_CONFIG:-$(ROOT)configs/datasets/selected.yaml})"
prepare: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && $(RUN) prepare $(PREP_ARGS)
test: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests/migration" -v
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests" -v
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python -m unittest discover -s "$(ROOT)tests/evaluation" -v

run: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && \
		"$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/run_catalog.py" \
		$(ARGS) $(if $(RGB_MAX),--rgb-max "$(RGB_MAX)",) $(if $(PLAN),--plan,) $(if $(JOBS),--jobs "$(JOBS)",)

evaluate: bootstrap
	$(SETUP) cd "$(ROOT)external/VSLAM-LAB" && "$$PIXI_BIN" run --frozen -e vslamlab python "$(ROOT)scripts/evaluate_result.py" \
		$(ARGS) $(if $(RUN_DIR),--run-dir "$(RUN_DIR)",) $(if $(EXPERIMENT),--experiment "$(EXPERIMENT)",) $(EVAL_ARGS)

else
DOCKER = VIO_ENV_FILE="$(ENV_FILE)" bash "$(ROOT)scripts/docker-compose.sh"
# Forward only workflow options, preserving each assignment as one argument.
DOCKER_OPTIONS = $(foreach option,CONFIG RGB_MAX PLAN JOBS RUN_DIR EXPERIMENT EVAL_ARGS,$(if $($(option)),"$(option)=$($(option))",))
.PHONY: build config shell artifacts
build: configure
	@$(DOCKER) build
config: configure
	@$(DOCKER) config
shell: configure
	@$(DOCKER) run --rm vio bash
artifacts: configure
	@$(DOCKER) run --rm vio python3 scripts/build_report_table.py --check
bootstrap prepare run evaluate test: configure
	@$(DOCKER) run --rm vio make $@ $(DOCKER_OPTIONS)
endif
