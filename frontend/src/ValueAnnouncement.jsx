import React, {useRef} from 'react';
import {createPortal} from 'react-dom';
import announcementHtml from '../public/value-announcement.html?raw';
import {LabelUsageContent} from './LabelManagement.jsx';
import './valueAnnouncement.css';

// Reuse only the maintained, build-time article; no remote HTML or user input.
const article = announcementHtml.match(/<article>([\s\S]*?)<\/article>/)[1];

export default function ValueAnnouncement() {
 const dialog=useRef(null),trigger=useRef(null);
 const open=()=>{if(!dialog.current.open)dialog.current.showModal();};
 const close=()=>dialog.current.close();
 return <>
  <button ref={trigger} type="button" className="button ghost" aria-haspopup="dialog" aria-controls="value-announcement" onClick={open}>使用说明</button>
  {createPortal(<dialog ref={dialog} id="value-announcement" className="value-announcement-dialog" aria-labelledby="value-announcement-heading" onClose={()=>trigger.current?.focus()}>
   <header className="va-header"><h2 id="value-announcement-heading">使用说明</h2><button type="button" className="va-close" aria-label="关闭使用说明" onClick={close}>×</button></header>
   <div className="va-body" tabIndex={0} aria-label="使用说明正文"><article><h2>配置、审批与当前加载</h2><p>在系统管理配置，在审批中先批准、再单独应用。已应用是配置记录，当前加载需另行核验。</p><p>Agent 助手只起草；运行事件只呈现真实回执。本期不提供自动运行时策略生成或热装载。</p><p>同一 Agent 进程的会话共享执行域。已加载不代表已经命中，也不代表覆盖所有操作。</p><h2>标签与信息流</h2><LabelUsageContent/></article><details><summary>能力说明与示意案例（不代表当前运行状态）</summary><article dangerouslySetInnerHTML={{__html:article}}/></details></div>
  </dialog>,document.body)}
 </>;
}
