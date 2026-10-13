"""Compatibility imports; implementation belongs to VSLAM-LAB Evaluate."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'external/VSLAM-LAB'))
from Evaluate.trajectory_inputs import read_pose_csv, to_evo, camera_to_body
