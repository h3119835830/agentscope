import React,{useEffect,useRef,useState} from 'react';
export default function PolicyLifecycleDialog({title,children,confirmLabel,onClose,onConfirm,busy=false}){
 const dialog=useRef(null),origin=useRef(document.activeElement),[pending,setPending]=useState(false),[error,setError]=useState('');
 const working=busy||pending;
 useEffect(()=>{dialog.current?.showModal();return()=>{dialog.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 return <dialog ref={dialog} className="policy-lifecycle-dialog" aria-label={title} onCancel={e=>{e.preventDefault();if(!working)onClose();}}><h2>{title}</h2><div>{children}</div>{error&&<p role="alert" className="inline-notice warning">{error}</p>}<footer><button className="button ghost" disabled={working} onClick={onClose}>取消</button><button className="button primary" disabled={working} onClick={async()=>{if(working)return;setPending(true);setError('');try{await onConfirm();}catch(e){setError(e.message);}finally{setPending(false);}}}>{working?'正在处理…':confirmLabel}</button></footer></dialog>;
}
