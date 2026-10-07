from pathlib import PurePosixPath
import pytest
from agentscope_app.workspaces.layout import snapshot_layout
from agentscope_app.policy_ir import PATTERN_MAX_UTF8_BYTES

ROOT = '/s/0123456789abcdef/r'
PROJECT = 'workspace/transaction-verification-service'

def entries(*paths):
    return [{'relative_path': path} for path in paths]

def test_nested_project_alias_preserves_internal_names_and_protected_exact_targets():
    original = [PROJECT+'/setup.py', PROJECT+'/tests/tests_rate_limiter.py', PROJECT+'/tests/test_validator.py', PROJECT+'/transaction-service/verification/customer_verifier.py', 'task.md', 'workspace/test_validator.py']
    mapping, prefixes = snapshot_layout(entries(*original), ROOT)
    assert prefixes == {PROJECT: 'p0'}
    for path in original[:4]:
        assert mapping[path] == 'p0/'+path.removeprefix(PROJECT+'/')
    assert mapping['task.md'] == 'task.md' and mapping['workspace/test_validator.py'] == 'workspace/test_validator.py'
    for path in original[1:3]:
        assert len((ROOT+'/'+mapping[path]).encode()) <= PATTERN_MAX_UTF8_BYTES

def test_short_projects_keep_identity_mapping():
    original = ['a/setup.py','a/main.py','a/tests/test_main.py']
    assert snapshot_layout(entries(*original), ROOT) == ({p:p for p in original}, {})

def test_aliases_are_deterministic_collision_free_for_multiple_project_roots():
    values = entries('p0', 'workspace/long-project-one-with-a-setup/setup.py', 'workspace/long-project-one-with-a-setup/tests/test_long_name.py', 'workspace/long-project-two-with-a-setup/setup.py', 'workspace/long-project-two-with-a-setup/main.py')
    mapping, prefixes = snapshot_layout(values, ROOT)
    assert sorted(prefixes.values()) == ['p1','p2']
    assert snapshot_layout(list(reversed(values)), ROOT)[1] == prefixes
    assert len(set(mapping.values())) == len(values)

def test_nested_package_is_not_moved_out_of_a_parent_build_project():
    original = ['package.json',PROJECT+'/setup.py',PROJECT+'/tests/tests_rate_limiter.py']
    assert snapshot_layout(entries(*original), ROOT) == ({p:p for p in original}, {})

def test_unrecognized_long_tree_and_unrepresentable_leaf_are_not_renamed_or_broadened():
    long_file = 'project/'+('测'*25)+'.py'
    original = ['project/setup.py', long_file, 'other-very-long-directory-without-project-marker/test_protected.py']
    mapping, prefixes = snapshot_layout(entries(*original), ROOT)
    assert mapping[long_file].endswith('/'+('测'*25)+'.py')
    assert len((ROOT+'/'+mapping[long_file]).encode()) > PATTERN_MAX_UTF8_BYTES
    assert mapping[original[2]] == original[2]
    assert all('*' not in path for path in mapping.values())

@pytest.mark.parametrize('path',['/absolute/file.py','a/../file.py','a//file.py',''])
def test_mapping_rejects_unsafe_or_noncanonical_relative_paths(path):
    with pytest.raises(ValueError, match='规范相对路径'):
        snapshot_layout(entries(path), ROOT)


def test_a_short_project_prefix_is_not_lengthened_to_alias_an_unrepresentable_leaf():
    original=['a/setup.py','a/'+('测'*25)+'.py']
    assert snapshot_layout(entries(*original), ROOT)==({p:p for p in original},{})
