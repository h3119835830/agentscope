#!/usr/bin/env python3
"""Disposable namespace entry and mini-swe-agent feedback adapter.

No production AgentScope APIs, credentials writes, or host policy mutations.
The outer root ActPlane runner owns the kernel event journal. Only its feedback
cursor is writable inside the namespace; the journal is mounted read-only.
"""
import json, os, subprocess, sys, time
from pathlib import Path


def enter():
    run = Path(sys.argv[2]); agent = sys.argv[3]
    state = os.environ.get('ACTPLANE_HOOK_STATE')
    args = ['/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--die-with-parent',
            '--cap-drop', 'ALL', '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
            '--ro-bind', '/etc', '/etc', '--ro-bind', '/mnt/wsl/resolv.conf', '/mnt/wsl/resolv.conf',
            '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    for source in ('/opt/agentscope/bin', '/opt/agentscope/dsh',
                   '/opt/agentscope/actplane/integrations/dsh-feedback',
                   '/opt/agentscope/integrations/dsh-agentscope',
                   '/var/lib/agentscope-four-scenarios-20261013/dsh-modules',
                   '/var/lib/agentscope-four-scenarios-20261013/venv',
                   '/var/lib/agentscope-four-scenarios-20261013/research/mini-swe-agent/src'):
        args += ['--ro-bind', source, source]
    args += ['--ro-bind', str(run), str(run), '--ro-bind', str(run/'actplane'), '/lab-actplane', '--bind', str(run/'work'), str(run/'work'),
             '--bind', str(run/'home'), str(run/'home'), '--ro-bind', __file__, '/lab-child.py']
    if state: args += ['--bind', state, state]
    args += ['--chdir', str(run/'work'), '--']
    env = dict(os.environ, HOME=str(run/'home'), DSH_HOME=str(run/'home/.dsh'),
               PATH='/opt/agentscope/bin:/var/lib/agentscope-four-scenarios-20261013/venv/bin:/usr/bin:/bin',
               PYTHONDONTWRITEBYTECODE='1', MSWEA_SILENT_STARTUP='1',
               PYTHONPATH='/var/lib/agentscope-four-scenarios-20261013/research/mini-swe-agent/src',
               MSWEA_GLOBAL_CONFIG_DIR=str(run/'home/.mini'))
    if agent == 'dsh':
        args += ['/usr/bin/python3', '/lab-child.py', 'dsh-run', str(run)]
    elif agent == 'mini':
        args += ['/var/lib/agentscope-four-scenarios-20261013/venv/bin/python', '/lab-child.py', 'mini', str(run)]
    else:
        args += ['/usr/bin/python3', str(run/'probe.py')]
    os.execve(args[0], args, env)


def mini():
    import yaml
    from minisweagent.agents.default import DefaultAgent
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.models.litellm_model import LitellmModel
    run = Path(sys.argv[2])
    credentials = yaml.safe_load((run/'home/.dsh/.credentials.yaml').read_text())
    key = credentials['refs']['DEEPSEEK_API_KEY']
    if isinstance(key, dict): key = key.get('value') or key.get('apiKey')
    class FeedbackEnvironment(LocalEnvironment):
        def __init__(self, **kwargs):
            super().__init__(**kwargs); self.offset = 0
        def execute(self, action, **kwargs):
            output = super().execute(action, **kwargs)
            time.sleep(.25)
            state = json.loads(Path(os.environ['ACTPLANE_HOOK_STATE']).read_text())
            path = Path(state['feedback_file'])
            data = path.read_text() if path.exists() else ''
            addition = data[self.offset:]; self.offset = len(data)
            if addition.strip():
                output['output'] += '\n[ActPlane 内核反馈]\n' + addition
            # Public tool observation only. Never serialize model responses/thinking.
            with (run/'home/public-mini.jsonl').open('a') as stream:
                stream.write(json.dumps({'command':action.get('command'), 'observation':output}, ensure_ascii=False)+'\n')
            return output
    model = LitellmModel(model_name='openai/deepseek-v4-flash', cost_tracking='ignore_errors',
                        model_kwargs={'api_base':'https://api.deepseek.com', 'api_key':key,
                                      'max_tokens':4096, 'temperature':0})
    environment = FeedbackEnvironment(cwd=str(run/'work'), timeout=90)
    agent = DefaultAgent(model, environment, system_template='你是一个通过 bash 工具完成任务的助手。用中文报告可观察的操作和结果。',
        instance_template='{{task}}\n每次至少调用一次 bash 工具。完成时单独执行 echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT，下一行用中文给出结果。',
        step_limit=24, cost_limit=3, wall_time_limit_seconds=720)
    result = agent.run((run/'task.txt').read_text())
    print(json.dumps({'exit_status':result.get('exit_status'), 'calls':agent.n_calls,
                      'submission':result.get('submission')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'enter':enter()
    elif sys.argv[1] == 'dsh-run':
        run=Path(sys.argv[2])
        command=['/opt/agentscope/bin/node', '/opt/agentscope/dsh/node_modules/.bin/dsh',
                 '--profile', 'headless', '--json', (run/'task.txt').read_text()]
        result=subprocess.run(command,stdout=open(run/'home/native.raw','w'),stderr=open(run/'home/native-stderr.txt','w'))
        sys.exit(result.returncode)
    else:mini()
