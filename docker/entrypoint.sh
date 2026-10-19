#!/usr/bin/env bash
# Prepare container-owned caches, then run as the owner of the mounted checkout.
set -euo pipefail
container_uid=$(stat -c '%u' /workspace/.git)
container_gid=$(stat -c '%g' /workspace/.git)
mkdir -p /home/vio/.cache/pixi
for container_cache in /home/vio /home/vio/.cache /home/vio/.cache/pixi /workspace/.tools \
    /workspace/external/VSLAM-LAB/.pixi \
    /workspace/external/VSLAM-LAB/Baselines/OKVIS1 \
    /workspace/external/VSLAM-LAB/Baselines/Voxel-SVIO \
    /workspace/external/VSLAM-LAB/Baselines/SqrtVINS \
    /workspace/external/VSLAM-LAB/Baselines/ORB-SLAM3; do
    if [[ $(stat -c '%u:%g' "$container_cache") != "$container_uid:$container_gid" ]]; then
        chown -R "$container_uid:$container_gid" "$container_cache"
    fi
done
# Compose may create missing output directories as root. Do not change existing
# datasets recursively: only the mount-point directories need to be writable.
for container_output in /data /results; do
    if [[ $(stat -c '%u:%g' "$container_output") != "$container_uid:$container_gid" ]]; then
        chown "$container_uid:$container_gid" "$container_output"
    fi
done
printf 'VIO container: uid=%s gid=%s; data=/data results=/results\n' "$container_uid" "$container_gid"
exec gosu "$container_uid:$container_gid" "$@"
