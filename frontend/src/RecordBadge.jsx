import React from 'react';
import {recordTone} from './recordTone.mjs';
export default function RecordBadge({children,tone,dot=true,mono=false}){
  return <span className={'record-badge tone-'+(tone||recordTone(children))+(mono?' record-badge-mono':'')}>{dot&&<span className="record-badge-dot" aria-hidden="true"/>}{children??'—'}</span>;
}
