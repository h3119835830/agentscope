"""Frozen project-root aliases; never rename package internals or broaden targets."""
from pathlib import PurePosixPath
from ..policy_ir import PATTERN_MAX_UTF8_BYTES

PROJECT_MARKERS = frozenset({'setup.py', 'pyproject.toml', 'package.json', 'Cargo.toml', 'go.mod', 'pom.xml', 'CMakeLists.txt'})


def snapshot_layout(entries, workspace):
    paths = [str(entry['relative_path']) for entry in entries]
    parts = {}
    for value in paths:
        path = PurePosixPath(value)
        if not path.parts or path.is_absolute() or '..' in path.parts or str(path) != value:
            raise ValueError('工作区快照路径必须是规范相对路径')
        parts[value] = path.parts
    project_roots = {value[:-1] for value in parts.values() if value[-1] in PROJECT_MARKERS}
    used = {value[0] for value in parts.values()}
    prefixes = {}
    for root in sorted(project_roots, key=lambda value: (len(value), value)):
        # The workspace root is fixed. Do not move a nested package out of a
        # parent project whose build/dependency references would be changed.
        if not root or any(root[:i] in project_roots for i in range(len(root))):
            continue
        members = [name for name, value in parts.items() if value[:len(root)] == root]
        if not any(len((str(workspace) + '/' + name).encode('utf-8')) > PATTERN_MAX_UTF8_BYTES for name in members):
            continue
        index = 0
        while 'p' + str(index) in used:
            index += 1
        alias = 'p' + str(index)
        if len('/'.join(root).encode('utf-8')) <= len(alias.encode('utf-8')):
            continue
        used.add(alias)
        prefixes['/'.join(root)] = alias
    mapping = {}
    for name in paths:
        prefix = next((prefix for prefix in prefixes if name.startswith(prefix + '/')), None)
        mapping[name] = prefixes[prefix] + name[len(prefix):] if prefix else name
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('工作区快照路径映射发生冲突')
    return mapping, prefixes
