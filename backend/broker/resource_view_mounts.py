"""AgentScope mount adapter. No ActPlane binary, ABI or compiler changes."""
import os
import stat
from pathlib import Path
from agentscope_app.instances import resource_views as views


def pin(source, expected=None):
    current = os.open('/', os.O_PATH | os.O_DIRECTORY)
    try:
        for part in Path(source).parts[1:]:
            next_fd = os.open(part, os.O_PATH | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = next_fd
        info = os.fstat(current)
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError('挂载来源不是普通目录或文件')
        if expected is not None and {'device': info.st_dev, 'inode': info.st_ino} != expected:
            raise ValueError('挂载来源身份已变化，拒绝启动')
        result, current = current, None
        return result
    finally:
        if current is not None:
            os.close(current)


def grant_arguments(resources, policy, fds):
    args=[]
    plan=policy['resource_views']
    for rule in sorted(policy['rules'],key=lambda r:(r['effect']=='deny',r['effect']=='deny' and r['action']=='read')):
        if rule['action'] not in ('read','write'):
            continue
        source=rule['target']
        target=views.translate(source,resources,plan)
        if rule['action']=='write':
            if rule['effect']=='deny' and any(Path(source) in Path(v['source']).parents for v in plan['views']):
                # Rebinding the host parent would erase the canonical links and
                # expose a second path to source files. Seal the projection.
                args += ['--remount-ro',target]
            else:
                expected=next((v['identity'] for v in plan['views'] if v['source']==source),None)
                fd=pin(source,expected);fds.append(fd)
                args += ['--bind-fd' if rule['effect']=='allow' else '--ro-bind-fd',str(fd),target]
        if rule['action']=='read' and rule['effect']=='deny' and Path(source).is_dir():
            args += ['--tmpfs',target,'--chmod','000',target]
    # Ancestor denies must cover all independent canonical mounts, too.
    for view in plan['views']:
        for rule in policy['rules']:
            if rule['effect']!='deny' or Path(rule['target']) not in Path(view['source']).parents:
                continue
            if rule['action']=='write':
                args += ['--remount-ro',view['execution']]
            if rule['action']=='read':
                args += ['--tmpfs',view['execution'],'--chmod','000',view['execution']]
    return args


def mount_arguments(resources, plan, *, probe=False):
    """Return bwrap arguments plus pinned source fds owned by the caller.

    Bind sources use bwrap's fd-consuming bind interface, not /proc/self/fd
    paths (which leave descriptors inherited by the untrusted payload). Close
    parent descriptors after Popen. Probe mode bypasses mount write restrictions
    so native kernel denies must independently pass startup acceptance.
    """
    operations = views.projection(resources, plan)
    args, fds = [], []
    try:
        for item in operations:
            kind, target = item['kind'], item['execution']
            if kind == 'directory':
                args += ['--perms','0555','--tmpfs', target]
            elif kind == 'seal':
                if not probe:
                    args += ['--remount-ro', target]
            elif kind == 'link':
                args += ['--symlink', item['target'], target]
            else:
                # Anchor each component: O_NOFOLLOW only on the final component
                # would still permit intermediate-directory replacement.
                fd=pin(item['source'],item['identity'])
                fds.append(fd)
                args += ['--bind-fd' if probe else '--ro-bind-fd',str(fd),target]
        return args, fds
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
