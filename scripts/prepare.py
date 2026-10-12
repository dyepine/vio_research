#!/usr/bin/env python3
"""Selective downloads and explicitly documented EuRoC-like VIO exports."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile

import numpy as np
from PIL import Image
import requests
from rosbags.highlevel import AnyReader
from scipy.spatial.transform import Rotation
import yaml
import zarr

from config_paths import config_path

ROOT = Path(__file__).resolve().parents[1]
DATASET_CONFIG_DIR = ROOT / 'configs' / 'datasets'
GB = 10**9
CAM_TOPICS = ['/dalsa_gray/left/image_raw', '/dalsa_gray/right/image_raw']


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def bytes_used(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file())


def checksum(path, spec):
    algorithm, expected = spec.split(':', 1)
    h = hashlib.new('sha1' if algorithm == 'git-sha1' else algorithm)
    if algorithm == 'git-sha1':
        h.update(f'blob {path.stat().st_size}\0'.encode())
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    if h.hexdigest() != expected:
        raise ValueError(f'Checksum mismatch: {path}; expected {spec}, got {h.hexdigest()}')


def safe_member(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError(f'Unsafe archive member: {name}')
    return p


def extract_tar(path, destination):
    """Never extract links, devices, or paths outside the destination."""
    with tarfile.open(path) as archive:
        for member in archive:
            rel = safe_member(member.name)
            out = destination.joinpath(*rel.parts)
            if member.isdir():
                out.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                out.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, out.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            else:
                raise ValueError(f'Unsupported archive member: {member.name}')


def download(asset, path, reserve_bytes):
    """Pinned URLs, verified content, Range resume, never trust size alone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.stat().st_size != asset['size']:
            raise ValueError(f'Unexpected existing file size: {path}')
        checksum(path, asset['checksum'])
        print(f'  verified cache: {path.name}', flush=True)
        return
    part = path.with_name(path.name + '.part')
    for attempt in range(4):
        offset = part.stat().st_size if part.exists() else 0
        if offset > asset['size']:
            raise ValueError(f'Oversized partial download: {part}')
        if offset == asset['size']:
            break
        if shutil.disk_usage(path.parent).free < asset['size'] - offset + reserve_bytes:
            raise RuntimeError(f'Insufficient free space for {path.name}')
        try:
            headers = {'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            print(f'  download: {path.name} ({asset["size"]/GB:.3f} GB), resume {offset}', flush=True)
            with requests.get(asset['url'], headers=headers, stream=True, timeout=(30, 90)) as r:
                r.raise_for_status()
                if offset and r.status_code == 200:
                    offset = 0  # server did not honor Range; restart, do not append
                elif r.status_code == 206:
                    content_range = r.headers.get('Content-Range', '')
                    if not content_range.startswith(f'bytes {offset}-'):
                        raise ValueError(f'Unexpected Content-Range: {content_range}')
                elif r.status_code != 200:
                    raise ValueError(f'Unexpected HTTP status: {r.status_code}')
                with part.open('ab' if offset else 'wb') as f:
                    for block in r.iter_content(4 * 1024 * 1024):
                        f.write(block)
                        if f.tell() > asset['size']:
                            raise ValueError(f'Remote file larger than manifest: {path}')
            if part.stat().st_size != asset['size']:
                raise requests.ConnectionError('Truncated response')
            break
        except (requests.RequestException, OSError):
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    checksum(part, asset['checksum'])
    part.replace(path)


def timestamps_ns(seconds):
    s = np.asarray(seconds)
    if s.ndim != 1 or len(s) < 2 or not np.isfinite(s).all():
        raise ValueError('Invalid or empty timestamp array')
    if s.min() <= 0 or s.max() >= np.iinfo(np.int64).max / 1e9:
        raise ValueError('Timestamp outside int64 nanosecond range')
    ns = np.rint(s * 1e9).astype(np.int64)
    check_times(ns)
    return ns


def check_times(ns):
    a = np.asarray(ns, dtype=np.int64)
    if len(a) < 2 or np.any(a <= 0) or np.any(np.diff(a) <= 0):
        raise ValueError('Timestamps must be positive, unique and strictly increasing')


def stamp_ns(header):
    return int(header.stamp.sec) * 10**9 + int(header.stamp.nanosec)


def csv_write(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def export_imu(out, times, gyro, accel):
    check_times(times)
    gyro, accel = np.asarray(gyro), np.asarray(accel)
    if gyro.shape != (len(times), 3) or accel.shape != gyro.shape:
        raise ValueError('IMU shape mismatch')
    if not np.isfinite(gyro).all() or not np.isfinite(accel).all():
        raise ValueError('Non-finite IMU measurements')
    csv_write(out / 'mav0/imu0/data.csv',
              ['#timestamp [ns]', 'w_x [rad/s]', 'w_y [rad/s]', 'w_z [rad/s]',
               'a_x [m/s^2]', 'a_y [m/s^2]', 'a_z [m/s^2]'],
              ([int(t), *w, *a] for t, w, a in zip(times, gyro, accel)))


def export_reference(out, times, pos, quat):
    check_times(times)
    pos, quat = np.asarray(pos), np.asarray(quat)
    if pos.shape != (len(times), 3) or quat.shape != (len(times), 4):
        raise ValueError('Reference shape mismatch')
    if not np.isfinite(pos).all() or not np.isfinite(quat).all():
        raise ValueError('Non-finite reference')
    norm = np.linalg.norm(quat, axis=1)
    if np.any(np.abs(norm - 1) > 0.01):
        raise ValueError('Reference has invalid quaternions; not silently normalizing')
    d = out / 'reference'
    d.mkdir(parents=True, exist_ok=True)
    with (d / 'poses.tum').open('w') as f:
        for t, p, q in zip(times, pos, quat):
            # Integer formatting avoids another loss of Unix timestamp precision.
            f.write(f'{int(t)//10**9}.{int(t)%10**9:09d} ' + ' '.join(f'{x:.12g}' for x in [*p, *q]) + '\n')


def transform(record):
    q, p = record['rotation'], record['translation']
    m = np.eye(4)
    m[:3, :3] = Rotation.from_quat([q[k] for k in ['x', 'y', 'z', 'w']]).as_matrix()
    m[:3, 3] = [p[k] for k in ['x', 'y', 'z']]
    return m


def relative_transform(records, parent, child):
    """GrandTour ZARR metadata maps parent -> child (NOT normal ROS TF).

    Publisher build_metadata.py uses lookupTransform(child_frame_id, orig_frame).
    Invert each record to obtain conventional T_parent_child for EuRoC.
    """
    adjacency = {}
    for rec in records.values():
        p, c = rec['base_frame_id'], rec['child_frame_id']
        m = np.linalg.inv(transform(rec))
        adjacency.setdefault(p, []).append((c, m))
        adjacency.setdefault(c, []).append((p, np.linalg.inv(m)))
    queue = [(parent, np.eye(4))]
    seen = set()
    while queue:
        current, m = queue.pop(0)
        if current == child:
            return m
        if current in seen:
            continue
        seen.add(current)
        queue.extend((n, m @ edge) for n, edge in adjacency.get(current, []) if n not in seen)
    raise ValueError(f'No static transform chain: {parent} -> {child}')


def camera_yaml(out, cam, info, T_BS):
    K = np.asarray(info['K']).reshape(3, 3)
    value = {'sensor_type': 'camera', 'camera_model': 'pinhole',
             'resolution': [info['width'], info['height']],
             'intrinsics': [float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2])],
             'distortion_model': info['distortion_model'], 'distortion_coefficients': info['D'],
             'T_BS': {'rows': 4, 'cols': 4, 'data': T_BS.ravel().tolist()},
             'source_frame': info['frame_id']}
    p = out / f'mav0/cam{cam}/sensor.yaml'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(value, sort_keys=False))


def write_imu_yaml(out, source_frame, source_noise=None):
    p = out / 'mav0/imu0/sensor.yaml'
    value = {'sensor_type': 'imu', 'T_BS': {'rows': 4, 'cols': 4, 'data': np.eye(4).ravel().tolist()},
             'source_frame': source_frame, 'units': {'angular_velocity': 'rad/s', 'specific_force': 'm/s^2'},
             'noise_parameters': source_noise,
             'note': 'No invented noise parameters. Configure each estimator explicitly.'}
    p.write_text(yaml.safe_dump(value, sort_keys=False))


def export_tar_images(path, times, out, cam, resolution):
    dest = out / f'mav0/cam{cam}/data'
    dest.mkdir(parents=True, exist_ok=True)
    seen = set()
    with tarfile.open(path) as archive:
        for member in archive:
            rel = safe_member(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f'Unsupported image archive member: {member.name}')
            if rel.suffix.lower() not in ['.jpeg', '.jpg', '.png']:
                raise ValueError(f'Unexpected image archive member: {member.name}')
            index = int(rel.stem)  # publication uses image index, NOT sequence_id
            if index >= len(times) or index < 0 or index in seen:
                raise ValueError(f'Invalid image index {index}')
            with archive.extractfile(member) as f, Image.open(f) as image:
                if list(image.size) != resolution:
                    raise ValueError(f'Image/calibration resolution mismatch: {image.size}')
                image.convert('L').save(dest / f'{int(times[index])}.png')
            seen.add(index)
    if len(seen) != len(times):
        raise ValueError(f'Missing images: {len(seen)} of {len(times)}')
    csv_write(dest.parent / 'data.csv', ['#timestamp [ns]', 'filename'],
              ([int(t), f'{int(t)}.png'] for t in times))


def array(group, key):
    return np.asarray(group[key][:])


def grandtour(spec, raw, out):
    data = out / '_zarr'
    data.mkdir()
    for asset in spec['files']:
        if asset['path'].startswith('data/') and asset['path'].endswith('.tar'):
            extract_tar(raw / asset['path'], data)
    groups = {p.name: zarr.open_group(str(p), mode='r') for p in data.iterdir() if p.is_dir()}
    imu = groups['adis_imu']
    export_imu(out, timestamps_ns(array(imu, 'timestamp')), array(imu, 'ang_vel'), array(imu, 'lin_acc'))
    imu_frame = imu.attrs['frame_id']
    records = dict(groups['tf'].attrs['tf'])
    for cam, key in enumerate(['zed2i_left_images', 'zed2i_right_images']):
        group = groups[key]
        times = timestamps_ns(array(group, 'timestamp'))
        if len(times) > math.ceil(spec['duration_bound_s'] * spec['image_rate_bound']):
            raise ValueError('Image count exceeds storage estimate; revise manifest first')
        info = dict(group.attrs['camera_info'])
        camera_yaml(out, cam, info, relative_transform(records, imu_frame, info['frame_id']))
        export_tar_images(raw / f'images/{key}.tar', times, out, cam, spec['resolution'])
    write_imu_yaml(out, imu_frame)
    ref = groups['cpt7_ie_tc_odometry']
    rt = timestamps_ns(array(ref, 'timestamp'))
    export_reference(out, rt, array(ref, 'pose_pos'), array(ref, 'pose_orien'))
    csv_write(out / 'reference/pose_covariance.csv', ['#timestamp [ns]', *[f'cov_{i}_{j}' for i in range(6) for j in range(6)]],
              ([int(t), *c.ravel()] for t, c in zip(rt, array(ref, 'pose_cov'))))
    prism = groups['prism_position']
    # Keep every field exactly as published; this is position-only, not pose GT.
    np.savez_compressed(out / 'reference/prism_original.npz', **{k: array(prism, k) for k in prism.array_keys()})
    attributes = {k: dict(g.attrs) for k, g in groups.items()}
    json_write(out / 'calibration/source_attributes.json', attributes)
    ref_frame = groups['cpt7_ie_tc_tf'].attrs['transform']['child_frame_id']
    m = relative_transform(records, imu_frame, ref_frame)
    json_write(out / 'reference/metadata.json', {
        'kind': 'GNSS_INS_offline_tightly_coupled', 'independent_of_visual_frontend': True,
        'world_frame': ref.attrs['frame_id'], 'tracked_frame': ref_frame,
        'quaternion_order': 'xyzw', 'T_imu_reference': m.tolist(),
        'transform_convention': 'p_imu = T_imu_reference @ p_reference; T_world_reference = T_world_imu @ T_imu_reference',
        'quality': 'Covariance is exported; no common quality mask has been applied.',
        'time': 'Published timestamps retained. Float seconds rounded to ns; this does not imply ns accuracy.',
        'prism': 'Position-only supplemental measurement; original fields and attributes retained.',
    })
    shutil.rmtree(data)  # only our temporary metadata extraction, not source archives


class OpenCVLoader(yaml.SafeLoader):
    pass


OpenCVLoader.add_constructor('tag:yaml.org,2002:opencv-matrix',
                            lambda loader, node: loader.construct_mapping(node, deep=True))


def opencv_yaml(path):
    return yaml.load(path.read_text().replace('%YAML:1.0', ''), Loader=OpenCVLoader)


def matrix(d):
    return np.array(d['data']).reshape(d['rows'], d['cols'])


def decode_ros_image(msg):
    if msg.encoding not in ['mono8', 'rgb8', 'bgr8']:
        raise ValueError(f'Unsupported image encoding: {msg.encoding}')
    channels = 1 if msg.encoding == 'mono8' else 3
    if msg.step < msg.width * channels:
        raise ValueError('Invalid image row stride')
    raw = np.asarray(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    pixels = raw[:, :msg.width * channels].reshape(msg.height, msg.width, channels)
    if channels == 1:
        return Image.fromarray(pixels[:, :, 0])
    if msg.encoding == 'bgr8':
        pixels = pixels[:, :, ::-1]
    return Image.fromarray(pixels).convert('L')


def botanicgarden(spec, raw, out):
    seq = spec['sequence']
    timestamps = [[], []]
    it, gyro, accel = [], [], []
    imu_frames = set()
    with AnyReader([raw / f'{seq}_VLIO.bag']) as reader:
        topics = set(CAM_TOPICS + ['/imu/data'])
        connections = [c for c in reader.connections if c.topic in topics]
        if {c.topic for c in connections} != topics:
            raise ValueError(f'Required camera/raw IMU topics missing; found {[c.topic for c in reader.connections]}')
        for c, _, data in reader.messages(connections=connections):
            msg = reader.deserialize(data, c.msgtype)
            t = stamp_ns(msg.header)  # not rosbag receive time
            if c.topic == '/imu/data':
                imu_frames.add(msg.header.frame_id)
                it.append(t)
                gyro.append([msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z])
                accel.append([msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z])
            else:
                cam = CAM_TOPICS.index(c.topic)
                if timestamps[cam] and t <= timestamps[cam][-1]:
                    raise ValueError('Camera timestamps not strictly increasing')
                with decode_ros_image(msg) as image:
                    if list(image.size) != spec['resolution']:
                        raise ValueError('Bag images are not the documented downsampled resolution')
                    dest = out / f'mav0/cam{cam}/data/{t}.png'
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    image.save(dest)
                timestamps[cam].append(t)
                if len(timestamps[cam]) > math.ceil(spec['duration_bound_s'] * spec['image_rate_bound']):
                    raise ValueError('Image count exceeds storage estimate')
    if len(imu_frames) != 1:
        raise ValueError(f'Inconsistent IMU frames: {imu_frames}')
    export_imu(out, it, gyro, accel)
    chain = opencv_yaml(raw / 'calib/extrinsics/calib_chain.yaml')
    T_BC0 = matrix(chain['T_xsens_gray0'])
    T_BC1 = T_BC0 @ matrix(chain['T_gray0_gray1'])
    for cam, T_BC in enumerate([T_BC0, T_BC1]):
        check_times(timestamps[cam])
        csv_write(out / f'mav0/cam{cam}/data.csv', ['#timestamp [ns]', 'filename'],
                  ([t, f'{t}.png'] for t in timestamps[cam]))
        calib = opencv_yaml(raw / f'calib/camera_intrinsics/dalsa_gray{cam}_down.yaml')
        p, d = calib['projection_parameters'], calib['distortion_parameters']
        info = {'K': [p['fx'], 0, p['cx'], 0, p['fy'], p['cy'], 0, 0, 1],
                'width': calib['image_width'], 'height': calib['image_height'],
                'D': [d[k] for k in ['k1', 'k2', 'p1', 'p2']],
                'distortion_model': 'radtan', 'frame_id': f'gray{cam}'}
        if [info['width'], info['height']] != spec['resolution']:
            raise ValueError('Calibration does not match bag resolution')
        camera_yaml(out, cam, info, T_BC)
    write_imu_yaml(out, next(iter(imu_frames)), opencv_yaml(raw / 'calib/imu_intrinsics/xsens_imu_param.yaml'))
    shutil.copytree(raw / 'calib', out / 'calibration/source')
    with zipfile.ZipFile(raw / 'GT_pose_qnew.zip') as archive:
        member = f'GT_pose_qnew/gt_{seq}_qnew.bag'
        gtbag = out / '_reference.bag'
        with archive.open(member) as src, gtbag.open('wb') as dst:
            shutil.copyfileobj(src, dst)
    times, pos, quat, frames = [], [], [], set()
    with AnyReader([gtbag]) as reader:
        connections = [c for c in reader.connections if c.topic == '/gt_poses']
        if not connections:
            raise ValueError('Corrected reference /gt_poses missing')
        for c, _, data in reader.messages(connections=connections):
            msg = reader.deserialize(data, c.msgtype)
            times.append(stamp_ns(msg.header))
            frames.add(msg.header.frame_id)
            p, q = msg.pose.position, msg.pose.orientation
            pos.append([p.x, p.y, p.z])
            quat.append([q.x, q.y, q.z, q.w])
    export_reference(out, times, pos, quat)
    gtbag.unlink()
    json_write(out / 'reference/metadata.json', {
        'kind': 'survey_map_registration_with_VIO_assistance', 'independent_of_visual_frontend': False,
        'tracked_frame': 'VLP16', 'world_frame': 'sequence-local surveyed map; unchanged',
        'source_header_frame_ids': sorted(frames), 'quaternion_order': 'xyzw',
        'T_imu_reference': matrix(chain['T_xsens_vlp16']).tolist(),
        'transform_convention': 'T_world_reference = T_world_imu @ T_imu_reference',
        'quality': 'No per-pose covariance or independent dynamic orientation bound supplied.',
        'time': 'Published header stamps retained; no invented time correction.',
        'reference_source': 'GT_pose_qnew.zip, not legacy GT poses in the VLIO bag',
        'camera1_extrinsics': 'Composed gray0/Xsens + stereo transform; independent gray1/Xsens retained in source calibration.',
    })


def load_csv(path):
    with path.open() as f:
        return list(csv.reader(line for line in f if not line.startswith('#')))


def validate(out):
    summary = {}
    intervals = []
    camera_times = []
    for cam in range(2):
        rows = load_csv(out / f'mav0/cam{cam}/data.csv')
        t = np.array([int(r[0]) for r in rows], dtype=np.int64)
        check_times(t)
        for ts, filename in rows:
            if filename != f'{ts}.png' or not (out / f'mav0/cam{cam}/data' / filename).is_file():
                raise ValueError('Missing image or invalid filename')
        with Image.open(out / f'mav0/cam{cam}/data' / rows[0][1]) as image:
            expected = yaml.safe_load((out / f'mav0/cam{cam}/sensor.yaml').read_text())['resolution']
            if list(image.size) != expected or image.mode != 'L':
                raise ValueError('Invalid converted image resolution/mode')
        camera_times.append(t)
        intervals.append((t[0], t[-1]))
        summary[f'cam{cam}'] = {'count': len(t), 'start_ns': int(t[0]), 'end_ns': int(t[-1]),
                                'max_gap_s': float(np.diff(t).max()/1e9)}
    rows = load_csv(out / 'mav0/imu0/data.csv')
    it = np.array([int(r[0]) for r in rows], dtype=np.int64)
    values = np.array([[float(v) for v in r[1:]] for r in rows])
    check_times(it)
    if values.shape[1] != 6 or not np.isfinite(values).all():
        raise ValueError('Invalid converted IMU')
    lo, hi = min(x[0] for x in intervals), max(x[1] for x in intervals)
    common_start = max(it[0], *(x[0] for x in intervals))
    common_end = min(it[-1], *(x[1] for x in intervals))
    if common_end <= common_start:
        raise ValueError('Camera and IMU intervals do not overlap')
    unbracketed = [int(np.count_nonzero((t < it[0]) | (t > it[-1]))) for t in camera_times]
    summary['usable_input_window_ns'] = [int(common_start), int(common_end)]
    summary['imu'] = {'count': len(it), 'max_gap_s': float(np.diff(it).max()/1e9),
                      'camera_frames_without_IMU_bracketing': unbracketed,
                      'median_accel_norm_m_s2': float(np.median(np.linalg.norm(values[:, 3:], axis=1)))}
    if any(unbracketed):
        print(f'WARNING: {unbracketed} boundary camera frames lack IMU bracketing. '
              'All data retained; use validation.json usable_input_window_ns for every method.', flush=True)
    rt, quats = [], []
    with (out / 'reference/poses.tum').open() as f:
        for line in f:
            r = line.split()
            sec, frac = r[0].split('.')
            rt.append(int(sec)*10**9 + int(frac.ljust(9, '0')))
            vals = np.asarray(r[1:], dtype=float)
            if len(vals) != 7 or not np.isfinite(vals).all():
                raise ValueError('Invalid reference pose')
            quats.append(vals[3:])
    rt = np.array(rt, dtype=np.int64)
    check_times(rt)
    if np.any(np.abs(np.linalg.norm(quats, axis=1)-1) > .01):
        raise ValueError('Invalid reference quaternion')
    overlap = max(0, min(hi, rt[-1])-max(lo, rt[0])) / (hi-lo)
    if overlap == 0:
        raise ValueError('Reference and camera times do not overlap')
    left, right = camera_times
    idx = np.searchsorted(right, left)
    distances = np.minimum(np.abs(left-right[np.clip(idx, 0, len(right)-1)]),
                           np.abs(left-right[np.clip(idx-1, 0, len(right)-1)]))
    summary['stereo_nearest_timestamp_difference_ms'] = {'median': float(np.median(distances)/1e6),
                                                       'max': float(distances.max()/1e6)}
    summary['reference'] = {'count': len(rt), 'temporal_extent_overlap_fraction': float(overlap),
                            'max_gap_s': float(np.diff(rt).max()/1e9),
                            'note': 'Extent overlap is NOT a quality mask or guaranteed coverage across gaps.'}
    json_write(out / 'validation.json', summary)
    return summary


def estimate_output(spec):
    # Grayscale PNG: use uncompressed pixel count plus 5% and metadata allowance.
    frames = math.ceil(spec['duration_bound_s'] * spec['image_rate_bound'])
    return int(2 * math.prod(spec['resolution']) * frames * 1.05 + .2 * GB)


def preflight(base, specs, max_bytes, reserve, include_download=True, include_output=True):
    existing = bytes_used(base)
    additional = 0
    for name, spec in specs.items():
        if include_download:
            for asset in spec['files']:
                p = base / 'raw' / name / asset['path']
                if not p.exists():
                    part = p.with_name(p.name + '.part')
                    additional += max(0, asset['size'] - (part.stat().st_size if part.exists() else 0))
        if include_output and not (base / 'processed' / name / 'complete.json').exists():
            additional += estimate_output(spec)
    print(f'Storage: existing {existing/GB:.2f} GB; additional estimate {additional/GB:.2f} GB; '
          f'free {shutil.disk_usage(base).free/GB:.2f} GB; reserve {reserve/GB:.2f} GB', flush=True)
    if existing + additional > max_bytes:
        raise RuntimeError(f'Estimated managed data {(existing+additional)/GB:.1f} GB > budget {max_bytes/GB:.1f} GB. Select fewer sequences.')
    if shutil.disk_usage(base).free < additional + reserve:
        raise RuntimeError(f'Need {additional/GB:.1f} GB additional + {reserve/GB:.1f} GB reserve; insufficient disk space.')


class ConfigLoader(yaml.SafeLoader):
    """Reject duplicate keys rather than silently changing selected recordings."""
    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise ValueError(f'Duplicate YAML key: {key}')
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_config(path, available):
    path = path.expanduser().resolve()
    value = yaml.load(path.read_text(), Loader=ConfigLoader)
    expected = {'data_dir', 'sequences', 'max_data_gb', 'reserve_gb'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f'Configuration must contain exactly {sorted(expected)}')
    if not isinstance(value['data_dir'], str) or not value['data_dir'].strip():
        raise ValueError('data_dir must be a nonempty path string')
    selected = value['sequences']
    if not isinstance(selected, dict) or not all(isinstance(k, str) and type(v) is bool for k, v in selected.items()):
        raise ValueError('sequences must be a mapping: sequence-name: true/false (not strings)')
    unknown = set(selected) - set(available)
    if unknown:
        raise ValueError(f'Unknown sequences in YAML: {sorted(unknown)}')
    for key in ['max_data_gb', 'reserve_gb']:
        number = value[key]
        if type(number) not in [int, float] or not math.isfinite(number):
            raise ValueError(f'{key} must be a finite number')
    if value['max_data_gb'] <= 0 or value['reserve_gb'] < 0:
        raise ValueError('Invalid storage limits in YAML')
    value['data_dir'] = config_path(value['data_dir'], path.parent)
    value['sequences'] = [name for name, active in selected.items() if active]
    if not value['sequences']:
        raise ValueError('No active sequences. Set at least one sequence to true in the YAML.')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('command', choices=['plan', 'prepare', 'download', 'convert', 'validate'])
    parser.add_argument('--config', type=Path, default=DATASET_CONFIG_DIR / 'prepare.yaml')
    args = parser.parse_args()
    manifest = json.loads((DATASET_CONFIG_DIR / 'datasets.json').read_text())
    try:
        settings = load_config(args.config, manifest['sequences'])
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(f'{args.config}: {exc}')
    specs = {name: manifest['sequences'][name] for name in settings['sequences']}
    base = settings['data_dir'].resolve()
    print(f'Config: {args.config.expanduser().resolve()}; data directory: {base}', flush=True)
    base.mkdir(parents=True, exist_ok=True)
    with (base / '.prepare.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name, spec in specs.items():
            print(f'{name}: sources {sum(a["size"] for a in spec["files"])/GB:.2f} GB; output upper estimate {estimate_output(spec)/GB:.2f} GB', flush=True)
        preflight(base, specs, settings['max_data_gb']*GB, settings['reserve_gb']*GB,
                  args.command in ['plan', 'prepare', 'download'], args.command in ['plan', 'prepare', 'convert'])
        if args.command == 'plan':
            print('Preflight OK. No dataset downloaded. PNG size is estimated, not measured.')
            return
        for name, spec in specs.items():
            raw, out = base / 'raw' / name, base / 'processed' / name
            if args.command in ['download', 'prepare']:
                for asset in spec['files']:
                    download(asset, raw / asset['path'], settings['reserve_gb']*GB)
            if args.command in ['convert', 'prepare']:
                identity = hashlib.sha256(json.dumps(spec, sort_keys=True).encode() + Path(__file__).read_bytes()).hexdigest()
                if out.exists():
                    marker = out / 'complete.json'
                    if not marker.exists() or json.loads(marker.read_text())['identity'] != identity:
                        raise RuntimeError(f'Existing output is incomplete or from another converter/version: {out}. Move it aside explicitly.')
                    validate(out)
                    print(f'  validated existing output: {out}')
                    continue
                for asset in spec['files']:
                    checksum(raw / asset['path'], asset['checksum'])
                out.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix=f'.{name}-', dir=out.parent) as temp:
                    work = Path(temp)
                    print(f'Converting {name} -> {out}', flush=True)
                    (grandtour if spec['dataset'] == 'grandtour' else botanicgarden)(spec, raw, work)
                    validate(work)
                    json_write(work / 'provenance.json', {'sequence': spec, 'source_revisions': manifest['sources'],
                               'converter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                               'image_conversion': 'grayscale uint8 PNG; no resize, rectification or timestamp shifts',
                               'format': 'EuRoC-like sensor layout + separate non-EuRoC reference; not a ready-made estimator configuration'})
                    json_write(work / 'complete.json', {'identity': identity})
                    work.rename(out)
                print(f'Complete: {out}', flush=True)
            if args.command == 'validate':
                if not (out / 'complete.json').exists():
                    raise RuntimeError(f'No completed conversion: {out}')
                print(json.dumps(validate(out), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
