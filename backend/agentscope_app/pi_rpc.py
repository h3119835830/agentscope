"""Bounded Pi RPC lifecycle; never persist assistant/reasoning/provider streams."""
import json,os,queue,signal,subprocess,threading,time

def drive(command,environment,prompt,status,trace,seconds=180,repairs=2):
    process=subprocess.Popen(command,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    inbox=queue.Queue()
    def consume():
        for line in iter(process.stdout.readline,b''):
            try:inbox.put(json.loads(line))
            except (ValueError,UnicodeError):inbox.put({'type':'invalid_record'})
        inbox.put({'type':'process_exit'})
    def discard():
        while process.stderr.read(8192):pass
    readers=[threading.Thread(target=f,daemon=True) for f in (consume,discard)]
    for reader in readers:reader.start()
    def send(message):
        process.stdin.write((json.dumps({'type':'prompt','message':message})+'\n').encode());process.stdin.flush()
    deadline=time.monotonic()+seconds;used=0
    try:
        send(prompt)
        while time.monotonic()<deadline:
            current=status()
            if current.get('cancelled'):raise ValueError('Pi analysis interrupted')
            try:event=inbox.get(timeout=min(.5,max(.01,deadline-time.monotonic())))
            except queue.Empty:continue
            typ=event.get('type')
            if typ=='tool_execution_start':
                trace({'kind':'tool_start','tool':event.get('toolName'),'args':event.get('args',{})})
            if typ=='tool_execution_end':
                result=event.get('result',{});error=bool(event.get('isError') or result.get('isError'))
                trace({'kind':'tool_end','tool':event.get('toolName'),'error':error,'diagnostic':(' '.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')[:2500] if error else None)})
            if typ=='response' and not event.get('success'):raise ValueError('Pi RPC command rejected')
            if typ in ('invalid_record','process_exit'):raise ValueError('Pi RPC process exited before submission')
            if typ=='agent_settled':
                current=status()
                if current.get('submitted'):return {'continuations':used,'protocol':'Pi RPC agent_settled; server submission verified'}
                if current.get('workflow_error'):raise ValueError(current['workflow_error'])
                if used>=repairs:
                    diagnostic=current.get('last_diagnostic')
                    raise ValueError('Pi settled without a server-validated submission'+(': '+str(diagnostic)[:2000] if diagnostic else ''))
                used+=1;diagnostic={k:v for k,v in current.items() if k not in ('cancelled','submitted')}
                trace({'kind':'workflow_continuation','number':used,'diagnostic':diagnostic})
                send('Control-plane workflow state: '+json.dumps(diagnostic)+'. The evidence and candidate workflow is incomplete. Continue the same conversation using the registered tools; correct diagnostics and submit. No task execution or approval is authorized.')
        raise ValueError('Pi exceeded its bounded analysis deadline')
    finally:
        process.stdin.close()
        if process.poll() is None:
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        for reader in readers:reader.join(timeout=1)
