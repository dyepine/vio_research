FROM ubuntu:22.04@sha256:0a9887931b0e38af2e3487ed39e29436b0535c4f3f52e57745baaf79d1898956

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates git make curl tar bzip2 unzip dpkg-dev python3 gosu \
      build-essential cmake pkg-config libopencv-dev libeigen3-dev libceres-dev \
      libgoogle-glog-dev libsuitesparse-dev libboost-filesystem-dev \
      libboost-system-dev libboost-thread-dev libboost-date-time-dev libyaml-cpp-dev \
      valgrind \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home --shell /bin/bash vio \
    && git config --system --add safe.directory /workspace \
    && git config --system --add safe.directory /workspace/external/VSLAM-LAB

ENV HOME=/home/vio \
    ROOT_DIR=/workspace \
    VIO_ENV_FILE=/opt/vio/env.sh \
    VIO_DATA_DIR=/data \
    VIO_RESULTS_DIR=/results \
    PIXI_BIN=/workspace/.tools/pixi \
    PIXI_CACHE_DIR=/home/vio/.cache/pixi \
    VIO_EXPERIMENT_CONFIG=/workspace/configs/experiments/report.yaml \
    VIO_DATASET_CONFIG=/workspace/configs/datasets/selected.yaml

RUN mkdir -p /workspace/.tools /workspace/external/VSLAM-LAB/.pixi \
      /workspace/external/VSLAM-LAB/Baselines/OKVIS1 \
      /workspace/external/VSLAM-LAB/Baselines/Voxel-SVIO \
      /workspace/external/VSLAM-LAB/Baselines/SqrtVINS \
      /workspace/external/VSLAM-LAB/Baselines/ORB-SLAM3 \
      /data /results \
    && chown -R 1000:1000 /workspace /home/vio /data /results
COPY scripts/env.sh /opt/vio/env.sh
COPY scripts/container-entrypoint.sh /usr/local/bin/vio-entrypoint
RUN chmod 755 /usr/local/bin/vio-entrypoint
COPY --chown=1000:1000 . /workspace
RUN mkdir -p /workspace/.git
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/vio-entrypoint"]
CMD ["make", "help"]
