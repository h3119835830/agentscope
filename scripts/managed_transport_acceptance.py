#!/usr/bin/env python3
"""Fixed, public Native operation during an isolated control-service outage."""
import hashlib,json,os,signal,sqlite3,sys,time,uuid
from pathlib import Path
from managed_control import api
STATE=Path('/var/lib/agentscope-scope-demo')
def run(task):
 if os.getuid()!=0:raise RuntimeError('Isolated process fault acceptance requires root')
 base='/api/managed/tasks/'+task
 before=api(base)['state'];native=api(base+'/native')
 assert before['phase']=='running' and before['gate']=='open' and native['status']=='idle'
 retry_before=native['transport']['retry_count'];recovered_before=native['transport']['recovered_calls']
 key='transport-'+uuid.uuid4().hex
 message="恢复验收：先读取当前权限，然后使用原生 bash 工具运行 Python：先 sleep 5 秒，再在当前工作区创建 transport-recovery.txt，内容仅为 public transport recovery\n，最后读取该文件确认结果。只操作此合法临时文件，不修改受保护对象，不申请扩权。"
 con=sqlite3.connect(STATE/'demo.sqlite3');con.row_factory=sqlite3.Row
 since=con.execute('SELECT COALESCE(MAX(id),0) FROM managed_events WHERE task_id=?',(task,)).fetchone()[0]
 api(base+'/prompt',{'text':message,'request_key':key})
 deadline=time.monotonic()+700;start=None
 while time.monotonic()<deadline:
  for row in con.execute("SELECT id,payload_json FROM managed_events WHERE task_id=? AND id>? AND kind='tool_start' ORDER BY id",(task,since)):
   payload=json.loads(row['payload_json'])
   if payload.get('name')=='bash':start={'event_id':row['id'],**payload};break
  if start:break
  time.sleep(.2)
 else:raise TimeoutError('Native bash operation did not start')
 assert not con.execute("SELECT id FROM managed_jobs WHERE status IN ('queued','running')").fetchall()
 assert not con.execute("SELECT id FROM history_jobs WHERE kind='task_bootstrap' AND status IN ('queued','running')").fetchall()
 service=json.loads((STATE/'service-pids.json').read_text())['api']
 assert str(STATE/'demo.sqlite3').encode() in Path('/proc',str(service),'environ').read_bytes()
 pid=start['pid'];assert Path('/proc',str(pid)).exists()
 paused_at=time.monotonic();os.kill(service,signal.SIGSTOP)
 print(json.dumps({'kind':'isolated_api_suspended','api_pid':service,'native_pid':pid,'tool_event_id':start['event_id']},ensure_ascii=False),flush=True)
 try:time.sleep(15)
 finally:os.kill(service,signal.SIGCONT)
 outage_seconds=time.monotonic()-paused_at
 from managed_acceptance import wait
 after,observed=wait(task,native['turn']+1,required_text=message)
 current=after['state'];target=Path('/s')/task/'r/transport-recovery.txt'
 data=target.read_bytes();assert b'public transport recovery' in data
 transport=observed['transport'];assert transport['retry_count']>retry_before and transport['recovered_calls']>recovered_before and transport['state']=='connected'
 assert current['session_id']==before['session_id'] and current['baseline_hash']==before['baseline_hash'] and current['version']==before['version'] and current['binding']['domain_id']==before['binding']['domain_id']
 assert Path('/proc',str(pid)).exists()
 protection=api(base+'/verify-operation',{'target':str(Path('/s')/task/'r/.bashrc'),'operation':'write','expected':'deny'})
 assert protection['classification']=='correct_block'
 report={'schema':'ManagedTransportRecovery/1','passed':True,'task':task,'session_id':current['session_id'],'api_pid':service,'native_pid':pid,'outage_seconds':outage_seconds,'request_key':key,'public_request_sha256':hashlib.sha256(message.encode()).hexdigest(),'tool_start_event_id':start['event_id'],'transport':transport,'file_sha256':hashlib.sha256(data).hexdigest(),'actual_native_user_message_delivered':any(e.get('type')=='user/message' and e.get('text')==message for e in observed['events']),'same_session_domain_policy_and_process':True,'policy_version':current['version'],'process_domain_id':current['binding']['domain_id'],'post_recovery_protected_write':protection['classification'],'state_after':'open_idle'}
 (STATE/'report/transport-recovery.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False),flush=True)
 con.close();return report
if __name__=='__main__':run(sys.argv[1])
