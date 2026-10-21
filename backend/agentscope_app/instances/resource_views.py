"""Pure, versioned short-path plans; constructing a plan grants no authority.

The executor projects readonly ancestor directories and replaces a selected
subtree with a symlink to its *only* canonical mount. It must not bind the same
host subtree twice: otherwise native path policies can be bypassed by aliases.
"""
import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

SCHEMA = 'agentscope.resource-views.v1'
MAX_VIEWS = 8
MAX_ENTRIES = 4096


def within(path, root):
    return path == root or root in path.parents


def identity(path):
    """Do not follow even an intermediate symlink when freezing authority."""
    p = Path(path)
    if not p.is_absolute() or str(p) != str(path) or '..' in p.parts:
        raise ValueError('映射路径必须为规范绝对路径')
    for part in [*reversed(p.parents), p]:
        try:
            value = part.lstat()
        except OSError as error:
            raise ValueError('映射目录必须已存在且可核验；申请不会创建目录') from error
        if stat.S_ISLNK(value.st_mode):
            raise ValueError('映射路径不能经过符号链接')
    if not stat.S_ISDIR(value.st_mode):
        raise ValueError('映射对象必须是目录')
    return {'device': value.st_dev, 'inode': value.st_ino}


def alias(source):
    # Stable across reboots and independent of view insertion order.
    return '/v/' + hashlib.sha256(source.encode()).hexdigest()[:12]


def freeze(resources, paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_VIEWS:
        raise ValueError('短路径映射需选择 1 至 8 个目录')
    if any(not isinstance(p,str) or len(p)>1000 for p in paths):
        raise ValueError('短路径映射来源格式不合法')
    roots = [Path(p) for p in resources]
    views = []
    for source in sorted(paths):
        p = Path(source)
        if not any(root in p.parents for root in roots):
            raise ValueError('短路径只能映射已有资源内的子目录，不能开放资源根或其他目录')
        if any(v['source'] == source for v in views):
            raise ValueError('短路径映射目录不能重复')
        views.append({'source': source, 'execution': alias(source), 'identity': identity(source)})
    if len({v['execution'] for v in views}) != len(views):
        raise ValueError('短路径发生冲突，拒绝映射')
    return {'schema': SCHEMA, 'views': views}


def validate(plan, resources):
    if not isinstance(plan, dict) or set(plan) != {'schema', 'views'} or plan['schema'] != SCHEMA:
        raise ValueError('短路径映射版本不受支持')
    views = plan['views']
    if not isinstance(views, list) or not 1 <= len(views) <= MAX_VIEWS:
        raise ValueError('短路径映射数量不合法')
    if any(not isinstance(v, dict) or set(v) != {'source', 'execution', 'identity'} for v in views):
        raise ValueError('短路径映射字段不合法')
    if any(not isinstance(v['source'], str) or len(v['source']) > 1000 for v in views):
        raise ValueError('短路径来源不合法')
    if any(not isinstance(v['identity'],dict) or set(v['identity'])!={'device','inode'} or
           any(type(n) is not int or n<0 for n in v['identity'].values()) for v in views):
        raise ValueError('短路径目录身份格式不合法')
    expected = freeze(resources, [v['source'] for v in views])
    if plan != expected:
        raise ValueError('映射目录身份或短路径已变化，请重新提交人工审批')
    return expected


def records(resources, plan=None):
    base = [{'source': p, 'execution': f'/w/{i}'} for i, p in enumerate(sorted(resources))]
    return base + ([{'source': v['source'], 'execution': v['execution']} for v in plan['views']] if plan else [])


def translate(value, resources, plan=None, reverse=False):
    p = PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts or str(p) != value:
        raise ValueError('资源路径必须是规范绝对路径')
    mounts = records(resources, plan)
    # First resolve either an old execution path or a new canonical one to host.
    for row in sorted(mounts, key=lambda r: len(r['execution']), reverse=True):
        base = PurePosixPath(row['execution'])
        if within(p, base):
            p = PurePosixPath(row['source']) / p.relative_to(base)
            break
    if reverse:
        return str(p)
    for row in sorted(mounts, key=lambda r: len(r['source']), reverse=True):
        base = PurePosixPath(row['source'])
        if within(p, base):
            return str(PurePosixPath(row['execution']) / p.relative_to(base))
    return str(p)


def owner(value, resources, plan=None):
    host = Path(translate(value, resources, plan, reverse=True))
    return next((r for r in sorted(records(resources, plan), key=lambda r: len(r['source']), reverse=True)
                 if within(host, Path(r['source']))), None)


def check_no_hardlinks(path, budget=MAX_ENTRIES):
    """Prevent writes via an already existing hardlink to protected material."""
    count = 0
    stack = [Path(path)]
    while stack:
        p = stack.pop()
        value = p.lstat()
        count += 1
        if count > budget:
            raise ValueError('映射目录条目超出核验限额，请缩小目录')
        if stat.S_ISLNK(value.st_mode) or (stat.S_ISREG(value.st_mode) and value.st_nlink != 1):
            raise ValueError('可写映射不能包含符号链接或硬链接别名')
        if stat.S_ISDIR(value.st_mode):
            stack.extend(p.iterdir())
        elif not stat.S_ISREG(value.st_mode):
            raise ValueError('可写映射只能包含普通目录和文件')


def projection(resources, plan):
    """Declarative mount plan, without mkdir/move/chmod or any host mutation.

    Only ancestors of diverted subtrees are enumerated. All other subtrees
    remain bound read-only. Original entrypoints become namespace-only links;
    host files and old session/workspace paths are left intact.
    """
    validate(plan, resources)
    mounts = records(resources, plan)
    output = []
    visited = 0
    for mount in mounts:
        root = Path(mount['source'])
        children = [v for v in plan['views'] if root in Path(v['source']).parents
                    and not any(root in Path(o['source']).parents and Path(o['source']) in Path(v['source']).parents
                                for o in plan['views'] if o != v)]
        if not children:
            output.append({'kind': 'bind', **mount, 'identity': identity(root)})
            continue
        diverted = {v['source']: v for v in children}
        def walk(path, execution):
            nonlocal visited
            visited += 1
            if visited > MAX_ENTRIES:
                raise ValueError('映射祖先目录条目超出核验限额')
            if str(path) in diverted:
                output.append({'kind': 'link', 'target': diverted[str(path)]['execution'], 'execution': execution})
                return
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                # Existing links in projected ancestors could target a new alias.
                raise ValueError('映射祖先目录含符号链接，请先核验目录布局')
            if any(path in Path(v).parents for v in diverted):
                # Synthetic ancestor nodes must not relax host DAC/ACL. Keep
                # this first profile conservative instead of guessing uid maps.
                if info.st_mode & 0o005 != 0o005 or 'system.posix_acl_access' in os.listxattr(path):
                    raise ValueError('映射祖先缺少公共只读遍历权限或含访问 ACL，不能安全投影')
                output.append({'kind': 'directory', 'execution': execution})
                for child in sorted(path.iterdir()):
                    walk(child, execution + '/' + child.name)
                output.append({'kind': 'seal', 'execution': execution})
            else:
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    raise ValueError('映射祖先目录包含不支持的特殊文件')
                output.append({'kind': 'bind', 'source': str(path), 'execution': execution,
                               'identity': {'device': info.st_dev, 'inode': info.st_ino}})
        walk(root, mount['execution'])
    return output
