"""Validate standard VSLAM-LAB camera/IMU CSVs and select a bracketed window."""
import csv

import numpy as np


def csv_rows(path):
    with path.open() as stream:
        reader = csv.reader(stream)
        next(reader)
        return list(reader)


def camera_imu_window(folder, start_frame=0):
    if type(start_frame) is not int or start_frame < 0:
        raise ValueError('start_frame must be a nonnegative integer')
    images = csv_rows(folder / 'rgb.csv')
    imu_rows = csv_rows(folder / 'imu_0.csv')
    if not images or len(imu_rows) < 2:
        raise ValueError('Empty camera stream or insufficient IMU samples')
    left = np.array([int(row[0]) for row in images], dtype=np.int64)
    right = np.array([int(row[2]) for row in images], dtype=np.int64)
    imu_t = np.array([int(row[0]) for row in imu_rows], dtype=np.int64)
    imu = np.array([[float(value) for value in row[1:]] for row in imu_rows])
    for timestamps in (left, right, imu_t):
        if np.any(np.diff(timestamps) <= 0):
            raise ValueError('Non-monotonic timestamps')
    if not np.isfinite(imu).all():
        raise ValueError('Non-finite IMU measurements')
    keep = ((left > imu_t[0]) & (right > imu_t[0]) &
            (left < imu_t[-1]) & (right < imu_t[-1]))
    keep[:start_frame] = False
    indices = np.flatnonzero(keep)
    if len(indices) < 100 or np.any(np.diff(indices) != 1):
        raise ValueError('Camera/IMU interval is too short or non-contiguous')
    start, end = int(indices[0]), int(indices[-1]) + 1
    audit = {
        'images_original': len(images), 'images_selected': end - start,
        'frame_interval': [start, end], 'frame_interval_convention': 'half-open [start, end)',
        'framework_rgb_idx_inclusive': [start, end - 1],
        'excluded_leading_frames': start, 'excluded_trailing_frames': len(images) - end,
        'selected_duration_s': float((left[end - 1] - left[start]) / 1e9),
        'stereo_max_timestamp_difference_ms': float(np.max(np.abs(left - right)) / 1e6),
        'imu_count': len(imu_t), 'imu_max_gap_ms': float(np.diff(imu_t).max() / 1e6),
    }
    if start_frame:
        audit['requested_start_frame'] = start_frame
    return images[start:end], audit
