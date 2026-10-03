"""Export observable actions and public assistant text, never replay/reasoning blocks."""
import hashlib
import json
import re
from pathlib import Path
from compression import zstd

def export_trace(task_root):
    actions=[];texts=[];models=[];sources=[]
    for file in (Path(task_root)/'.dsh/sessions').rglob('*.jsonl.zstd'):
        sources.append({'path':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        with zstd.open(file,'rt') as stream:
            for line in stream:
                record=json.loads(line);kind=record.get('type');data=record.get('data',{})
                if kind=='request/header':
                    config=data.get('header',{}).get('config',{})
                    models.append({k:config[k] for k in ('model','provider','reasoningEffort','maxTokens') if k in config})
                if kind=='assistant/message':
                    message=data.get('message',{})
                    for block in message.get('content',[]):
                        if block.get('type')=='text' and isinstance(block.get('text'),str):texts.append(block['text'])
                if kind=='tool/call':
                    raw=data.get('arguments','');safe={}
                    try:
                        parameters=json.loads(raw)
                        for key,value in parameters.items():
                            if key in ('path','file_path','workdir','command','cmd','pattern') and isinstance(value,str) and not re.search(r'(?i)token|credential|api.?key|authorization|password|secret|reasoning|\.env',value):safe[key]=value
                    except (ValueError,TypeError,AttributeError):pass
                    actions.append({'time':record.get('time'),'name':data.get('name'),'call_id':data.get('callId'),
                                    'argument_hash':hashlib.sha256(raw.encode()).hexdigest(),'observable_parameters':safe})
    return {'session_sources':sources,'model_configuration':models,'assistant_text':'\n'.join(texts),'tool_actions':actions,'reasoning_exported':False}
