import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from agentscope_app.instances import resource_views as views
from agentscope_app.instances.policy import canonical, restrictive
from broker.resource_view_mounts import mount_arguments,grant_arguments
from broker.instance_runtime import policy_dsl


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / 'root'
    project = root / ('scene-' + 'x' * 65) / 'workspace' / 'project'
    source, output, tests = [project / p for p in ('src', 'acceptance-artifacts', 'tests')]
    for p in (source, output, tests):
        p.mkdir(parents=True, exist_ok=True)
    (source / 'code.py').write_text('code\n')
    (tests / 'test.py').write_text('immutable\n')
    (project / 'README.md').write_text('read me\n')
    plan = views.freeze([str(root)], [str(project), str(source), str(output)])
    return dict(root=root, project=project, source=source, output=output, tests=tests,
                resources=[str(root)], plan=plan)


def rule(path, effect='allow'):
    return {'action':'write', 'target':str(path), 'effect':effect, 'text':''}


def policy(layout):
    return canonical({'network':'disabled', 'resource_views':layout['plan'],
                      'rules':[rule(layout['source']), rule(layout['output']), rule(layout['tests'], 'deny')]},
                     layout['resources'])


def test_canonical_paths_do_not_depend_on_insertion_order(layout):
    x = layout
    target = str(x['source'] / 'code.py')
    old = '/w/0/' + str(Path(target).relative_to(x['root']))
    short = views.translate(target, x['resources'], x['plan'])
    assert len(short.encode()) < 63
    assert views.translate(old, x['resources'], x['plan']) == short
    assert views.translate(short, x['resources'], x['plan'], reverse=True) == target
    assert x['plan'] == views.freeze(x['resources'], [v['source'] for v in reversed(x['plan']['views'])])
    assert not restrictive({'network':'disabled','rules':[]}, policy(x))


def test_native_dsl_keeps_parents_and_tests_readonly(layout):
    x = layout
    text = policy_dsl(x['resources'], policy(x))
    assert 'block write file "/w/0/**"' in text
    assert f'block write file "{views.alias(str(x["project"]))}/**"' in text
    assert f'block write file "{views.alias(str(x["project"]))}/tests/**"' in text
    for key in ('source', 'output'):
        assert f'block write file "{views.alias(str(x[key]))}/**"' not in text
    assert 'unless target' not in text


def test_inherited_deny_covers_diverted_subtrees(layout):
    x = layout
    p = policy(x)
    p['rules'].append(rule(x['project'], 'deny'))
    text = policy_dsl(x['resources'], p)
    assert f'block write file "{views.alias(str(x["source"]))}/**"' in text
    assert f'block write file "{views.alias(str(x["output"]))}/**"' in text


def test_parent_write_grant_is_rejected(layout):
    x = layout
    p = policy(x)
    p['rules'].append(rule(x['project']))
    with pytest.raises(ValueError, match='父目录'):
        canonical(p, x['resources'])


@pytest.mark.parametrize('fault', ['root','foreign','duplicate','symlink','inode','alias','schema','hardlink','missing'])
def test_plan_fails_closed_on_identity_or_boundary_change(layout, tmp_path, fault):
    x = layout
    if fault in ('root','foreign','duplicate','symlink'):
        p = x['root'] if fault == 'root' else tmp_path if fault == 'foreign' else x['source']
        if fault == 'symlink':
            p = x['project'] / 'link'; p.symlink_to(x['source'])
        with pytest.raises(ValueError):
            views.freeze(x['resources'], [str(p)] * (2 if fault == 'duplicate' else 1))
    elif fault == 'missing':
        missing=x['project']/'not-created'
        with pytest.raises(ValueError,match='不会创建目录'):
            views.freeze(x['resources'],[str(missing)])
        assert not missing.exists()
    elif fault == 'hardlink':
        os.link(x['tests'] / 'test.py', x['source'] / 'alias.py')
        with pytest.raises(ValueError, match='硬链接'):
            policy(x)
    else:
        if fault == 'inode':
            x['output'].rename(x['project'] / 'retained-output')
            x['output'].mkdir()
        if fault == 'alias':
            x['plan']['views'][0]['execution'] = '/w/0'
        if fault == 'schema':
            x['plan']['schema'] = 'unknown'
        with pytest.raises(ValueError):
            views.validate(x['plan'], x['resources'])


def test_projection_only_replaces_namespace_entries_not_host_files(layout):
    x = layout
    operations = views.projection(x['resources'], x['plan'])
    assert sum(o['kind'] == 'link' for o in operations) == 3
    for source in (x['project'], x['source'], x['output']):
        assert not source.is_symlink()
        binds = [o for o in operations if o['kind'] == 'bind' and o['source'] == str(source)]
        assert len(binds) == (0 if source == x['project'] else 1)


def test_real_bwrap_parent_protection_and_single_canonical_path(layout):
    """Real mount namespace, synthetic fixture only; no Agent/service restart."""
    if sys.platform != 'linux' or not Path('/usr/bin/bwrap').exists():
        pytest.skip('Linux bwrap required; skip is not runtime acceptance')
    x = layout
    args, fds = mount_arguments(x['resources'], x['plan'])
    source = views.alias(str(x['source']))
    output = views.alias(str(x['output']))
    project = views.alias(str(x['project']))
    # The two approved leaf directories only. Parent/test bindings stay ro.
    args += grant_arguments(x['resources'],policy(x),fds)
    old_project = '/w/0/' + str(x['project'].relative_to(x['root']))
    program = r'''
import json,os
from pathlib import Path
paths=json.loads(os.environ['FIXTURE'])
result={}
for key,path in paths.items():
    try:
        Path(path).write_text('probe\n')
        result[key]=True
    except OSError:
        result[key]=False
result['canonical']=str(Path(paths['old_source']).resolve())
result['inherited_fds']=[f for f in os.listdir('/proc/self/fd') if int(f)>2 and os.path.exists('/proc/self/fd/'+f)]
print(json.dumps(result))
'''
    paths = {'source':source+'/probe.txt', 'output':output+'/probe.txt',
             'parent':project+'/escape.txt', 'root':'/w/0/escape.txt',
             'test':project+'/tests/test.py', 'old_source':old_project+'/src/legacy.txt',
             'old_test':old_project+'/tests/test.py'}
    try:
        result = subprocess.run(['/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--die-with-parent',
                                 '--cap-drop','ALL', '--ro-bind','/usr','/usr','--symlink','usr/lib','/lib',
                                 '--symlink','usr/lib64','/lib64','--proc','/proc', '--dev','/dev',
                                 *args, '--', '/usr/bin/python3','-c',program],
                                pass_fds=fds, capture_output=True, text=True, timeout=15,
                                env={'FIXTURE':json.dumps(paths)})
    finally:
        for fd in fds:
            os.close(fd)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert {k:v for k,v in value.items() if k in paths} == {
        'source':True,'output':True,'parent':False,'root':False,'test':False,'old_source':True,'old_test':False}
    assert value['canonical'] == source + '/legacy.txt'
    assert value['inherited_fds'] == []
    assert (x['tests'] / 'test.py').read_text() == 'immutable\n'


def test_projection_cannot_widen_host_directory_permissions(layout):
    layout['project'].chmod(0o700)
    with pytest.raises(ValueError,match='遍历权限'):
        views.projection(layout['resources'],layout['plan'])


def test_parent_deny_preserves_canonical_links_in_mount_plan(layout):
    x=layout;p=policy(x);p['rules'].append(rule(x['project'],'deny'))
    args,fds=mount_arguments(x['resources'],x['plan'])
    try:
        restriction=grant_arguments(x['resources'],p,fds)
        for key in ('project','source','output'):
            assert any(restriction[i:i+2]==['--remount-ro',views.alias(str(x[key]))] for i in range(len(restriction)))
    finally:
        for fd in fds:os.close(fd)


def test_session_context_resolves_old_and_canonical_paths_without_widening(layout):
    from agentscope_app.history import agent_context
    from agentscope_app.instances.template_configurations import path_parameter
    x=layout
    old='/w/0/'+str(x['project'].relative_to(x['root']))
    context={'workspace':old,'environment_binding':{'values':{
        'workspace':{'host':str(x['project'])},'resources':x['resources'],'resource_views':x['plan']}},
        'verified_targets':[],'allowed_paths':[]}
    expected=views.alias(str(x['source']))+'/code.py'
    for path in ('src/code.py',old+'/src/code.py',expected):
        bound=agent_context.bind_targets(context,[{'path':path}])
        fact=bound['environment_binding']['values']['target_paths'][0]
        assert fact['path']==expected and fact['inode']==(x['source']/'code.py').stat().st_ino
    with pytest.raises(ValueError,match='超出当前会话'):
        agent_context.bind_targets(context,[{'path':'/w/0/outside.txt'}])
    row={'resources':x['resources'],'policy':policy(x)}
    assert path_parameter(old+'/src/code.py',row)==expected
