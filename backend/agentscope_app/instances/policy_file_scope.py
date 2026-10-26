"""Turn an operator's named reading sources into an enforced body-read scope.

Only operator text selects sources. Project documents and model tool arguments
cannot widen this scope. Directory metadata remains available for verification.
"""
import re
from pathlib import PurePosixPath
from . import workspace_references as refs


def selected_paths(text):
    paths = []
    for clause in re.split(r'[，,。；;\n]', text):
        if not re.search(r'读取|阅读|查阅|根据|参照|依据|\b(?:read|review|consult|based on)\b', clause, re.I):
            continue
        if re.search(r'不(?:要|得|能|允许)?(?:读取|阅读)|禁止(?:读取|阅读)|\b(?:do not|never|deny)\s+read\b', clause, re.I):
            continue
        tokens = re.findall(r'/?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', clause)
        tokens += re.findall(r'[`“"]([^`”"\n]+)[`”"]', clause)
        for token in tokens:
            if PurePosixPath(token).suffix.lower() not in refs.TEXT_EXTENSIONS and token not in {'AGENTS', 'Dockerfile', 'Makefile'}:
                continue
            refs.paths_checked([token])
            if token not in paths:
                paths.append(token)
    return refs.paths_checked(paths) if paths else None
