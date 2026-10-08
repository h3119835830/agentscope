"""Adapter contract: observations are never enforcement receipts."""
from typing import Protocol
from ..broker_client import call

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
        return self.invoke('start',instance,agent_type=instance['agent_type'],resources=instance['resources'],policy=instance['policy'],policy_hash=instance['policy_hash'],token=token,generation=generation)
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
