"""Adapter contract: observations are never enforcement receipts."""
from typing import Protocol
from ..broker_client import call

def entry_details(instance):
    """Describe an entry, never infer a CLI from a generic OS process name."""
    controlled=instance.get('mode')=='controlled' and instance.get('agent_type') in ('dsh','hermes')
    kind='web' if controlled or instance.get('runtime',{}).get('open_url') else instance.get('entry_kind','process')
    labels={'web':'Web','cli':'CLI','cli_install':'CLI 安装入口','desktop':'桌面应用','process':'进程观测'}
    if kind not in labels: kind='process'
    result={'kind':kind,'label':labels[kind]}
    if controlled:
        result['instructions']='已运行时点击“打开网页”；未运行时点击“启动网页”，由 AgentScope 加载此实例策略并核验后打开原生网页。'
    elif kind=='cli_install' and instance.get('id')=='installed-wsl-hermes':
        result['command']='wsl -d Ubuntu -u happy -- /home/happy/.local/bin/hermes'
        result['instructions']='这是 WSL 原生 Hermes 的 CLI 安装入口，不是已运行的会话。命令在 Windows 终端运行；需要网页时，在 AgentScope 添加 Hermes 受控连接并点击“启动网页”。直接运行 CLI 尚未接入实例策略。'
    elif kind=='web':
        result['instructions']='已连接的入口可直接打开网页。未连接时请检查原生服务；打开操作不会重启已有实例。'
    elif kind=='desktop':
        result['instructions']='这是 OS 发现的桌面应用进程，目前没有接入窗口打开接口；请从系统应用入口打开。'
    elif kind=='cli':
        result['instructions']='这是 CLI 进程，需要从它所属的终端使用；当前没有接入终端恢复接口。'
    else:
        result['instructions']='仅识别到 OS 进程，尚不能判定它是 Web、CLI 还是共享执行器。不会据此生成打开地址。'
    return result

class AgentAdapter(Protocol):
    def observe(self, instance: dict) -> dict: ...
    def open(self, instance: dict) -> dict: ...
    def start(self, instance: dict, token: str, generation: str) -> dict: ...
    def stop(self, instance: dict) -> dict: ...
    def sessions(self, instance: dict) -> dict: ...
    def processes(self, instance: dict) -> dict: ...
    def events(self, instance: dict, before: int | None = None) -> list: ...

class LocalAdapter:
    def invoke(self, op, instance, **body):
        return call({'action':'agent-instance-'+op, 'instance_id':instance['id'], **body}, timeout=90 if op in ('start','verify') else 35 if op=='stop' else 3)
    def observe(self, instance): return self.invoke('observe',instance)
    def open(self, instance): return self.invoke('open',instance)
    def start(self, instance, token, generation):
        from .dsl_policy import launch_spec
        return self.invoke('start',instance,agent_type=instance['agent_type'],resources=instance['resources'],policy=instance['policy'],policy_hash=instance['policy_hash'],token=token,generation=generation,**launch_spec(instance))
    def stop(self, instance): return self.invoke('stop',instance)
    def sessions(self, instance): return self.invoke('sessions',instance)
    def processes(self, instance): return self.invoke('processes',instance)
    def events(self, instance, before=None):
        from . import store
        return store.events(instance['id'],before)

def adapter(instance):
    if instance['environment']!='wsl' or instance['agent_type'] not in ('dsh','hermes'):
        raise ValueError('此连接仅支持观测，未接入受控启动适配器')
    return LocalAdapter()
