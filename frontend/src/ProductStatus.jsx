import React,{useEffect,useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import {currentStatus} from './productStatus.mjs';

export function useEvidenceClock(expiresAt){
 const [now,setNow]=useState(Date.now);
 useEffect(()=>{
  setNow(Date.now());
  const expiry=Date.parse(expiresAt);
  if(!Number.isFinite(expiry))return;
  const timer=setTimeout(()=>setNow(Date.now()),Math.max(0,expiry-Date.now()+1));
  return()=>clearTimeout(timer);
 },[expiresAt]);
 return now;
}
export default function ProductStatus({value,dimension='loading',failed=false}){
 const now=useEvidenceClock(value?.expires_at),status=currentStatus(value,dimension,Math.max(now,Date.now()),failed);
 return <RecordBadge tone={['loaded','running'].includes(status.state)?'good':['checking','starting','paused'].includes(status.state)?'warn':'neutral'}>{status.label}</RecordBadge>;
}
