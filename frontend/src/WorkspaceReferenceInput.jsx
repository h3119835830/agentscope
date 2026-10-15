import React,{useEffect,useRef,useState} from 'react';

export default function WorkspaceReferenceInput({targetId,api,post,onChange}){
 const [data,setData]=useState(null),[workspace,setWorkspace]=useState(''),[paths,setPaths]=useState(''),[receipt,setReceipt]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const sequence=useRef(0),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;sequence.current++;};},[]);
 const invalidate=(nextWorkspace,nextPaths)=>{sequence.current++;setBusy(false);setReceipt(null);setError('');onChange({pending:!!(nextWorkspace&&nextPaths.trim()),receipt:null});};
 async function load(){try{const value=await api('/api/agent-instances/'+encodeURIComponent(targetId)+'/policy-reference-workspaces');if(alive.current){setData(value);setError('');}}catch(e){if(alive.current){setData(null);setError(e.message);}}}
 async function read(){if(busy||!workspace||!paths.trim())return;const current=++sequence.current;setBusy(true);setError('');setReceipt(null);onChange({pending:true,receipt:null});
  try{const value=await post('/api/agent-instances/'+encodeURIComponent(targetId)+'/policy-workspace-reads',{workspace_id:workspace,paths:paths.split('\n').map(v=>v.trim()).filter(Boolean),request_key:crypto.randomUUID()});
   if(alive.current&&current===sequence.current){setReceipt(value);onChange({pending:false,receipt:value});}
  }catch(e){if(alive.current&&current===sequence.current)setError(e.message);}finally{if(alive.current&&current===sequence.current)setBusy(false);}
 }
 return <details className="workspace-reference-input" onToggle={e=>{if(e.currentTarget.open&&!data&&!busy)load();}}><summary>读取工作区参考文件{receipt?' · 已读取 '+receipt.files.length+' 个文件':''}</summary>
 <p className="field-note">通过接口读取此 Agent 已登记且允许读取的文本，结合系统策略与已有模板填写参数。资料不决定作用范围，读取不会应用策略。</p>
 {data&&<><label>参考工作区<select aria-label="参考工作区" value={workspace} onChange={e=>{setWorkspace(e.target.value);invalidate(e.target.value,paths);}}><option value="">请选择已登记资源目录</option>{data.workspaces.map(w=><option key={w.id} value={w.id}>{w.name} · {w.execution_path}</option>)}</select></label>{!data.workspaces.length&&<p>此 Agent 没有已登记资源目录。</p>}
 <label>参考文件<textarea aria-label="参考文件相对路径" rows={3} maxLength={10000} value={paths} onChange={e=>{setPaths(e.target.value);invalidate(workspace,e.target.value);}} placeholder={'每行一个相对路径，例如：\nREADME.md\ndocs/requirements.md'}/></label>
 <p className="field-note">最多 10 个文件，每个 64 KiB，合计 192 KiB。凭据、私钥、符号链接和不允许读取的对象会被拒绝。</p>
 <div className="workspace-reference-actions"><button type="button" className="button tiny ghost" disabled={busy||!workspace||!paths.trim()} onClick={read}>{busy?'正在读取…':'读取参考文件'}</button><button type="button" className="assistant-text-button" onClick={()=>{setWorkspace('');setPaths('');invalidate('','');}}>取消参考</button></div></>}
 {error&&<p role="alert" className="inline-notice warning">{error} {!data&&<button type="button" className="assistant-text-button" onClick={load}>重新读取目录</button>}</p>}
 {receipt&&<div className="workspace-reference-sources"><p>已读取 {receipt.workspace_name} 中的 {receipt.files.length} 个文件；生成和提交时会重新核对。</p>{receipt.files.map(f=><details key={f.relative_path}><summary>{f.relative_path} · {f.byte_size} B</summary><pre>{f.text}</pre></details>)}</div>}
 </details>;
}
