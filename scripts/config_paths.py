"""Resolve explicit environment placeholders in YAML path fields."""
import os
from pathlib import Path
from string import Template


def config_path(value, parent):
    try:
        expanded = Template(value).substitute(os.environ)
    except KeyError as error:
        raise ValueError(f'Environment variable {error.args[0]} is unset; run via make or source .envrc') from error
    path = Path(expanded).expanduser()
    return path if path.is_absolute() else parent / path
