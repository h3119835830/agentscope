"""Remove explicitly named, unused label-acceptance BPF pins, not evidence."""
import os
from pathlib import Path
import re
import sys


def main(names):
    assert os.geteuid()==0 and names
    targets=[]
    for name in names:
        if not re.fullmatch(r'(?:lf-[a-z0-9_]{8}|lfperf-[a-z0-9_]{8}-[0-4]-(?:baseline|transitions)|agentscope-label-flow-as-flow-[a-z0-9_]{8})',name):
            raise ValueError('Not an isolated label acceptance pin root')
        root=Path('/sys/fs/bpf')/name
        if not root.exists():continue
        assert root.parent==Path('/sys/fs/bpf') and root.resolve()==root and not root.is_symlink()
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():continue
            try:environment=(process/'environ').read_bytes()
            except (FileNotFoundError,ProcessLookupError):continue
            if str(root).encode() in environment:
                raise RuntimeError('Pin root still referenced by a live process: '+name)
        targets.append(root)
    # Every target is validated before removing any. All services have already
    # been stopped via identity-checked acceptance teardown.
    for root in targets:
        for path in sorted(root.rglob('*'),key=lambda p:len(p.parts),reverse=True):
            if path.is_symlink():raise RuntimeError('Unexpected symlink in test pins')
            if path.is_dir():path.rmdir()
            else:path.unlink()
        root.rmdir()
        print('Removed isolated test pins: '+root.name)


if __name__=='__main__':main(sys.argv[1:])
