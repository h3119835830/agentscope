"""Bounded Pi RPC lifecycle; never persist assistant/reasoning/provider streams."""
import json,os,queue,signal,subprocess,threading,time

def drive(command,environment,prompt,status,trace,seconds=180,repairs=2,required_skill=None):
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
    def rpc(value):
        process.stdin.write((json.dumps(value)+'\n').encode());process.stdin.flush()
    def send(message):rpc({'type':'prompt','message':message})
    deadline=time.monotonic()+seconds;used=0;finalize_used=False
    discovered=False;verifying=False
    try:
        if required_skill:rpc({'type':'get_commands','id':'feedback-skill-discovery'})
        else:send(prompt)
        while time.monotonic()<deadline:
            current=status()
            if current.get('cancelled'):raise ValueError('Pi analysis interrupted')
            try:event=inbox.get(timeout=min(.5,max(.01,deadline-time.monotonic())))
            except queue.Empty:continue
            typ=event.get('type')
            if typ=='response' and event.get('id')=='feedback-skill-discovery':
                skills=[c.get('name') for c in event.get('data',{}).get('commands',[]) if c.get('source')=='skill']
                if not event.get('success') or skills!=['skill:'+required_skill['name']]:
                    raise ValueError('Pi required feedback skill was not exclusively discovered')
                discovered=True
                send('/skill:'+required_skill['name']+' '+prompt)
                continue
            if typ=='response' and event.get('id')=='feedback-skill-context':
                # Inspect only public user inputs. Never persist provider or assistant streams.
                messages=event.get('data',{}).get('messages',[])
                inputs=[''.join(c.get('text','') for c in m.get('content',[]) if c.get('type')=='text')
                        if isinstance(m.get('content'),list) else m.get('content','')
                        for m in messages if m.get('role')=='user']
                marker='<skill name="'+required_skill['name']+'" location="'+required_skill['metadata']['mount']+'">'
                if not event.get('success') or not inputs or not inputs[0].startswith(marker) or required_skill['body'] not in inputs[0]:
                    raise ValueError('Pi feedback skill body was not admitted into native context')
                return {'continuations':used,'protocol':'Pi RPC agent_settled; server submission verified',
                        'skill':{'name':required_skill['name'],'discovery_verified':discovered,'context_verified':True}}
            if typ=='tool_execution_start':
                trace({'kind':'tool_start','tool':event.get('toolName'),'args':event.get('args',{})})
            if typ=='tool_execution_end':
                result=event.get('result',{});error=bool(event.get('isError') or result.get('isError'))
                trace({'kind':'tool_end','tool':event.get('toolName'),'error':error,'diagnostic':(' '.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')[:2500] if error else None)})
            if typ=='response' and not event.get('success'):raise ValueError('Pi RPC command rejected')
            if typ in ('invalid_record','process_exit'):raise ValueError('Pi RPC process exited before submission')
            if typ=='agent_settled':
                current=status()
                if current.get('submitted'):
                    if not required_skill:return {'continuations':used,'protocol':'Pi RPC agent_settled; server submission verified'}
                    if not verifying:
                        verifying=True;rpc({'type':'get_messages','id':'feedback-skill-context'})
                    continue
                if current.get('workflow_error'):raise ValueError(current['workflow_error'])
                if current.get('force_finalize'):
                    if finalize_used:
                        raise ValueError('Pi settled without a server-validated submission after tool budget exhaustion')
                    finalize_used=True;used+=1
                    trace({'kind':'workflow_finalization','number':used,'diagnostic':{
                        'force_finalize':True,'remaining_tool_calls':0,'allowed_next_tools':['submit_analysis']}})
                    send('Control-plane workflow state: the tool budget is exhausted. Do not call any tool except submit_analysis. '
                         'Submit the existing server-verified candidates now; if none can be submitted, use an empty configurations array and report exact questions and gaps. '
                         'No task execution, approval, loading, or new investigation is authorized.')
                    continue
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
