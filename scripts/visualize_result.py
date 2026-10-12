#!/usr/bin/env python3
"""Display a saved evo evaluation without recomputing its metrics."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from evo.tools import file_interface

from config_paths import config_path
from run_results import select_run

ROOT = Path(__file__).resolve().parents[1]


def send_transforms(rr, entity, trajectory):
    # evo 1.35.2 send_transforms rolls a flattened quaternion array; roll each pose instead.
    rr.send_columns(entity, indexes=[rr.TimeColumn('time', timestamp=trajectory.timestamps)],
                    columns=rr.Transform3D.columns(translation=trajectory.positions_xyz,
                            quaternion=np.roll(trajectory.orientations_quat_wxyz, -1, axis=1)))
    rr.log(entity, rr.TransformAxes3D.from_fields(axis_length=0.4), static=True)


def initialize_recording(rr, save):
    rr.init('vio_evo_evaluation', spawn=False)
    if save is not None:
        rr.save(str(save))
    else:
        # An absolute Python invocation does not activate its venv or update PATH.
        # Use the matching SDK's viewer, never an unrelated rerun on the caller's PATH.
        executable = Path(sys.executable).parent / ('rerun.exe' if sys.platform == 'win32' else 'rerun')
        if not executable.is_file():
            raise FileNotFoundError(f'Rerun viewer missing from Python environment: {executable}')
        rr.spawn(executable_path=str(executable))


def metric_style(name, summary):
    is_ape = name.startswith('ape_')
    quantity = 'position (m)' if name.endswith('position_m') else 'orientation (deg)'
    label = f'APE {quantity}' if is_ape else f"RPE {quantity}, {summary['protocol']['rpe_delta_m']:g} m GT"
    return ([255, 150, 0] if is_ape else [170, 100, 255]), label


def error_view(rr, rrb, summary, quantity, title):
    entities = {f'/errors/{quantity}/{name}': name for name in summary['metrics'] if name.endswith(quantity)}
    styles = {}
    for entity, name in entities.items():
        color, label = metric_style(name, summary)
        styles[entity] = rr.SeriesLines.from_fields(colors=color, names=label, visible_series=[True])
    end_s = max(segment['end_s'] for segment in summary['matched_segments'])
    y_max = max((summary['metrics'][name]['max'] for name in entities.values()), default=1.0)
    # Reset the initial viewport, rather than retaining a zoom around the final APE samples.
    # RPE may end much earlier than APE; both need to fit in the starting view.
    return rrb.TimeSeriesView(origin=f'/errors/{quantity}', contents=list(entities), name=title,
                              overrides=styles, plot_legend=rrb.PlotLegend(visible=True),
                              axis_x=rrb.TimeAxis(view_range=rr.TimeRange(
                                  start=rrb.TimeRangeBoundary.absolute(seconds=0),
                                  end=rrb.TimeRangeBoundary.absolute(seconds=max(end_s * 1.02, 1))),
                                  zoom_lock=False),
                              axis_y=rrb.ScalarAxis(range=(0, max(y_max * 1.05, 1e-6)), zoom_lock=False))


def log_recording(evaluation, save=None):
    import rerun as rr
    import rerun.blueprint as rrb
    from evo.tools import rerun_bridge as bridge

    summary = json.loads((evaluation / 'summary.json').read_text())
    ape = file_interface.load_res_file(evaluation / 'ape_position_m.zip', load_trajectories=True)
    reference, estimate = ape.trajectories['reference'], ape.trajectories['estimate']
    initialize_recording(rr, save)
    rr.send_blueprint(rrb.Blueprint(rrb.Horizontal(
        rrb.Vertical(rrb.Spatial3DView(origin='world', name='Matched estimate vs GT (metres)'),
                     rrb.Horizontal(error_view(rr, rrb, summary, 'position_m', 'APE / RPE position (m)'),
                                    error_view(rr, rrb, summary, 'orientation_deg', 'APE / RPE orientation (deg)'))),
        rrb.TextDocumentView(origin='summary', name='Protocol and diagnostics'), column_shares=[3, 1])))
    rr.log('summary', rr.TextDocument(json.dumps(summary, indent=2)), static=True)
    rr.log('world', rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
    # Full paths remain visible when the time cursor moves. Sparse keyframes are
    # vertices of a polyline, not proof of a tracking failure between them.
    groups = [np.arange(estimate.num_poses)]
    intervals = summary['protocol'].get('gt_valid_intervals_ns')
    if intervals:
        origin = summary['time_origin_ns']
        groups = [np.flatnonzero((estimate.timestamps >= (start - origin) / 1e9) &
                                 (estimate.timestamps <= (end - origin) / 1e9))
                  for start, end in intervals]
    for name, trajectory, color in [('estimate', estimate, [255, 150, 0]),
                                    ('reference', reference, [0, 200, 255])]:
        strips = [trajectory.positions_xyz[ids] for ids in groups if len(ids) >= 2]
        rr.log(f'world/{name}_path', rr.LineStrips3D(strips, colors=color, radii=0.015), static=True)
    gap_ids = np.flatnonzero(np.diff(estimate.timestamps) > summary['protocol']['max_pose_gap_s'])
    if len(gap_ids):
        midpoints = (estimate.positions_xyz[gap_ids] + estimate.positions_xyz[gap_ids + 1]) / 2
        labels = [f'{estimate.timestamps[i+1] - estimate.timestamps[i]:.2f} s between saved poses'
                  for i in gap_ids]
        rr.log('world/sparse_intervals', rr.Points3D(midpoints, radii=0.035, colors=[160, 160, 160],
                                                   labels=labels, show_labels=False), static=True)
    # One current correspondence, rather than one carried-forward marker per segment.
    reference.timestamps = estimate.timestamps
    bridge.send_correspondence_strips('world/residual', reference, estimate,
                                     bridge.ui_points_radii(1), bridge.Color(static=[255, 60, 100]))
    send_transforms(rr, 'world/estimate', estimate)
    send_transforms(rr, 'world/reference', reference)
    for name in summary['metrics']:
        result = file_interface.load_res_file(evaluation / (name + '.zip'))
        color, label = metric_style(name, summary)
        bridge.send_scalars('errors/' + ('position_m' if name.endswith('position_m') else 'orientation_deg') + '/' + name, result.np_arrays['error_array'],
                           bridge.Color(static=color),
                           timestamps=result.np_arrays['timestamps'], labelname=label)
        print(f'{label}: {len(result.np_arrays["error_array"])} values', flush=True)
    rr.get_global_data_recording().flush()
    if save:
        save.with_suffix('.json').write_text(json.dumps(summary, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir')
    parser.add_argument('--evaluation-dir', type=Path, help='Exact saved evaluation; default newest in selected run')
    parser.add_argument('--save', type=Path)
    args = parser.parse_args()
    if args.evaluation_dir:
        evaluation = args.evaluation_dir.expanduser().resolve()
    else:
        run = select_run(args.run_dir, config_path('${VIO_RESULTS_DIR}', ROOT) if not args.run_dir else ROOT)
        evaluation = select_run(None, run / 'evaluations',
                                required_files=('summary.json', 'protocol.yaml', 'ape_position_m.zip'))
    if not (evaluation / 'summary.json').exists():
        raise FileNotFoundError('No completed evaluation; run make evaluate first')
    save = args.save.expanduser().resolve() if args.save else None
    if save:
        if save.suffix != '.rrd':
            raise ValueError('--save must have an .rrd extension')
        if save.exists() or save.with_suffix('.json').exists():
            raise FileExistsError('Export already exists; select a new --save path')
        save.parent.mkdir(parents=True, exist_ok=True)
    log_recording(evaluation, save)
    print('Recording:' if save else 'Evaluation:', save or evaluation)


if __name__ == '__main__':
    main()
