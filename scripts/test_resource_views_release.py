import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import deploy_resource_views as release


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_only_scope_demo_units(self):
        self.assertEqual(set(release.DROPS), {release.API, release.BROKER})
        with self.assertRaises(RuntimeError):
            release.drop_text('agentscope-api.service', self.root)

    def test_drops_keep_reduced_api_launcher_and_readiness(self):
        api = release.drop_text(release.API, self.root)
        broker = release.drop_text(release.BROKER, self.root)
        self.assertIn('TimeoutStopSec=3', api)
        self.assertIn('scope_systemd_exec.py api-ready', api)
        self.assertIn('scope_systemd_exec.py broker-ready', broker)
        self.assertNotIn('User=', api)
        self.assertNotIn('Environment=', api)

    def test_historical_rows_may_only_be_appended(self):
        release.verify_retained({'events': ['a']}, {'events': ['a', 'b']})
        with self.assertRaises(RuntimeError):
            release.verify_retained({'events': ['a']}, {'events': ['b']})

    def test_native_mismatch_fails_closed(self):
        with patch.object(release, 'sha', return_value='wrong'):
            with self.assertRaises(RuntimeError):
                release.native_hash()

    def test_busy_jobs_block_before_service_mutation(self):
        with patch.object(release, 'database') as database:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)
            with self.assertRaisesRegex(RuntimeError, 'In-flight'):
                release.idle()

    def test_live_execution_blocks_release(self):
        with patch.object(release, 'database') as database, patch.object(release, 'execution_inventory') as inventory:
            database.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
            inventory.return_value = {'manifests': [], 'processes': {'cgroup.procs': ['123']}}
            with self.assertRaisesRegex(RuntimeError, 'Live managed'):
                release.idle()

    def test_private_exclusive_manifest(self):
        path = self.root / 'manifest.json'
        release.write_private(path, {'safe': True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text()), {'safe': True})
        with self.assertRaises(FileExistsError):
            release.write_private(path, {})

    def static_fixture(self):
        state = self.root / 'state'
        staged = self.root / 'release'
        for base in (state / 'ui', staged / 'frontend/dist'):
            (base / 'assets').mkdir(parents=True)
            (base / 'index.html').write_text('old' if base.parent == state else 'new')
            (base / 'terminal.html').write_text('terminal')
        (state / 'ui/assets/old.js').write_text('keep')
        (staged / 'frontend/dist/assets/new.js').write_text('new asset')
        return state, staged

    def test_publish_retains_old_assets(self):
        state, staged = self.static_fixture()
        with patch.object(release, 'STATE', state):
            release.publish_static(staged)
        self.assertEqual((state / 'ui/index.html').read_text(), 'new')
        self.assertEqual((state / 'ui/assets/old.js').read_text(), 'keep')
        self.assertEqual((state / 'ui/assets/new.js').read_text(), 'new asset')

    def test_asset_collision_fails_before_index_switch(self):
        state, staged = self.static_fixture()
        (state / 'ui/assets/new.js').write_text('different')
        with patch.object(release, 'STATE', state):
            with self.assertRaisesRegex(RuntimeError, 'collision'):
                release.publish_static(staged)
        self.assertEqual((state / 'ui/index.html').read_text(), 'old')

    def test_invalid_manifest_has_no_service_side_effect(self):
        with patch.object(release, 'run_systemctl') as systemctl:
            with self.assertRaises(RuntimeError):
                release.apply(str(self.root / 'manifest.json'))
        systemctl.assert_not_called()

    def test_verification_failure_restores_only_code_and_ui_pointers(self):
        state, staged = self.static_fixture()
        backup = self.root / 'backup'
        (backup / 'ui').mkdir(parents=True)
        for name in ('index.html', 'terminal.html'):
            (backup / 'ui' / name).write_text('original ' + name)
        drops = {release.API: self.root / 'api.conf', release.BROKER: self.root / 'broker.conf'}
        result = {'published': False, 'restored_agents': []}
        with patch.multiple(release, STATE=state, DROPS=drops), \
             patch.object(release, 'run_systemctl') as systemctl, patch.object(release, 'idle'), \
             patch.object(release, 'verify_release', side_effect=RuntimeError('fixture failure')), \
             patch.object(release, 'health'):
            with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
                release.switch({}, staged, backup, result)
        self.assertTrue(result['code_pointers_rolled_back'])
        self.assertFalse(result['published'])
        self.assertEqual(result['restored_agents'], [])
        self.assertFalse(any(path.exists() for path in drops.values()))
        self.assertEqual((state / 'ui/index.html').read_text(), 'original index.html')
        self.assertFalse((backup / 'demo.sqlite3').exists())
        starts = [call.args for call in systemctl.call_args_list if call.args[0] == 'start']
        self.assertTrue(all(args[1] in (release.API, release.BROKER) for args in starts))
        self.assertEqual(json.loads((backup / 'result.json').read_text())['failure_type'], 'RuntimeError')

    def test_runtime_contract_has_no_agent_start_or_approval_mutations(self):
        text = Path(release.__file__).read_text()
        self.assertNotIn("'/start'", text)
        self.assertNotIn('agent-instance-start', text)
        self.assertNotIn('UPDATE ', text)
        self.assertNotIn('DELETE ', text)
        self.assertNotIn('INSERT ', text)
        self.assertNotIn('method=', text)


if __name__ == '__main__':
    unittest.main()
