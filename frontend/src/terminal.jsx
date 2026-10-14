import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Terminal} from '@xterm/xterm';
import {FitAddon} from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import './terminal.css';
async function request(url,body){const response=await fetch(url,{method:body?'POST':'GET',credentials:'omit',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const value=await response.json();if(!response.ok)throw Error(value.detail||'终端连接失败');return value;}
function App(){
 const mount=useRef(null),[name,setName]=useState('Agent 终端'),[status,setStatus]=useState('正在核验连接…'),[error,setError]=useState('');
 const id=window.location.pathname.split('/').pop();
 useEffect(()=>{
  let alive=true,timer,inputTimer,row,cursor=0,queue=Promise.resolve(),polling=false,pendingInput='';
  const terminal=new Terminal({cursorBlink:true,fontSize:14,theme:{background:'#101827',foreground:'#dce6f2'},convertEol:false,scrollback:3000});
  const fit=new FitAddon();terminal.loadAddon(fit);terminal.open(mount.current);fit.fit();terminal.focus();
  function send(action,extra={}){
   queue=queue.then(async()=>{
    if(!alive||!row)return;
    const value=await request('/api/agent-instances/'+encodeURIComponent(id)+'/terminal',{generation:row.generation,policy_hash:row.policy_hash,action,cursor,...extra});
    if(!alive)return;
    if(value.generation!==row.generation||!Number.isInteger(value.pid)||value.pid<=0)throw Error('终端返回身份不一致，请重新打开');
    setStatus('执行受控 · PID '+value.pid);
    if(value.truncated)terminal.writeln('\r\n[较早输出已移出缓冲区]');
    if(value.data)terminal.write(Uint8Array.from(atob(value.data),c=>c.charCodeAt(0)));
    cursor=value.cursor;
    if(value.exit_code!==null){setStatus('进程已结束');alive=false;}
   }).catch(e=>{if(alive){setError(e.message);setStatus('执行暂停或连接中断');alive=false}});
   return queue;
  }
  const input=terminal.onData(data=>{pendingInput+=data;clearTimeout(inputTimer);inputTimer=setTimeout(()=>{const bytes=new TextEncoder().encode(pendingInput);pendingInput='';for(let i=0;i<bytes.length;i+=6000)send('write',{data:btoa(String.fromCharCode(...bytes.slice(i,i+6000)))});},20);});
  const observer=new ResizeObserver(()=>{fit.fit();if(row)send('resize',{cols:Math.max(10,Math.min(300,terminal.cols)),rows:Math.max(4,Math.min(150,terminal.rows))})});observer.observe(mount.current);
  request('/api/agent-instances/'+encodeURIComponent(id)).then(value=>{
   if(!alive)return;if(value.gate!=='open'||value.launch?.kind!=='terminal')throw Error('此连接没有正在受控运行的终端，请回到 Agent 连接打开');
   row=value;setName(value.name);setStatus('正在核验终端保护…');send('resize',{cols:Math.max(10,Math.min(300,terminal.cols)),rows:Math.max(4,Math.min(150,terminal.rows))});
   timer=setInterval(async()=>{if(polling||!alive)return;polling=true;try{await send('read')}finally{polling=false}},350);
  }).catch(e=>{if(alive){setError(e.message);setStatus('未连接')}});
  return()=>{alive=false;clearInterval(timer);clearTimeout(inputTimer);observer.disconnect();input.dispose();terminal.dispose()};
 },[id]);
 return <main className="terminal-page"><header><div><b>{name}</b><span>{status}</span></div><a href={'/?view=connections&connectionInstance='+encodeURIComponent(id)}>连接设置 ↗</a></header>{error&&<p role="alert">{error} <button onClick={()=>window.location.reload()}>重新连接</button></p>}<div ref={mount} className="terminal-surface" aria-label="Agent 交互终端"/><footer>关闭此标签页仅断开显示。停止进程请在 Agent 连接中操作。</footer></main>;
}
createRoot(document.getElementById('root')).render(<App/>);
