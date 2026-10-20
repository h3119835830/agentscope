"""Capabilities attested for this installed binary; never trust browser flags."""
import hashlib
import json
import platform
from pathlib import Path

def installed(binary):
    binary=Path(binary);manifest=binary.with_name(binary.name+'.capabilities.json')
    result={'verified':False,'file_suffix':False,'max_suffix_bytes':0,'reason':'当前执行环境尚未核验文件后缀能力'}
    try:
        info=manifest.lstat();bin_info=binary.stat();parent=binary.parent.stat()
        if manifest.is_symlink() or binary.is_symlink() or info.st_uid!=0 or info.st_mode&0o022 or bin_info.st_uid!=0 or bin_info.st_mode&0o022 or parent.st_uid!=0 or parent.st_mode&0o022:return result
        data=json.loads(manifest.read_text())
        actual=hashlib.sha256(binary.read_bytes()).hexdigest()
        if data.get('binary_sha256')!=actual or data.get('schema')!='agentscope.execution-capabilities.v1' or data.get('runtime_verified') is not True:return result
        if data.get('file_suffix') is not True or data.get('max_suffix_bytes')!=63:return result
        if data.get('kernel_release')!=platform.release():return result
        return {'verified':True,'file_suffix':True,'max_suffix_bytes':63,'binary_sha256':actual,'reason':'','profile':'controlled-suffix-v1'}
    except (OSError,ValueError,TypeError):return result

def loaded_features(record):
    """Read the kernel's actual feature reservation, not the executable's claim."""
    import subprocess
    pin=record.get('pin_root')
    if not pin:return None
    result=subprocess.run(['/usr/sbin/bpftool','-j','map','lookup','pinned',str(Path(pin)/'maps/engine_features'),'key','hex','00','00','00','00'],capture_output=True,text=True,timeout=3)
    if result.returncode:return None
    try:
        value=json.loads(result.stdout)['value']
        if isinstance(value,int):return value
        if isinstance(value,dict):return value.get('value')
        return int.from_bytes(bytes(int(x,16) if isinstance(x,str) else x for x in value),'little')
    except (ValueError,KeyError,TypeError):return None


def loaded_flow_status(record):
    """Kernel map presence/counters, never capability claims from the browser."""
    import subprocess
    pin=record.get('pin_root')
    if not pin:
        return {'transitions_supported':None}
    root=Path(pin)/'maps'
    if not (root/'flow_rb').exists():
        return {'transitions_supported':False}
    result={'transitions_supported':True,'lost_events':None}
    try:
        output=subprocess.run(['/usr/sbin/bpftool','-j','map','lookup','pinned',str(root/'flow_counters'),
                               'key','hex','01','00','00','00'],capture_output=True,text=True,timeout=2)
        if output.returncode:
            return result
        value=json.loads(output.stdout)['value']
        if isinstance(value,dict):value=value.get('value')
        result['lost_events']=value if isinstance(value,int) else int.from_bytes(bytes(int(x,16) if isinstance(x,str) else x for x in value),'little')
    except (OSError,ValueError,TypeError,KeyError,subprocess.TimeoutExpired):
        pass
    return result
