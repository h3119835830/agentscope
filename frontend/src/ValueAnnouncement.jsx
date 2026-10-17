import React, {useRef} from 'react';
import {createPortal} from 'react-dom';
import announcementHtml from '../public/value-announcement.html?raw';
import './valueAnnouncement.css';

// Reuse only the maintained, build-time article; no remote HTML or user input.
const article = announcementHtml.match(/<article>([\s\S]*?)<\/article>/)[1];

export default function ValueAnnouncement() {
 const dialog=useRef(null),trigger=useRef(null);
 const open=()=>{if(!dialog.current.open)dialog.current.showModal();};
 const close=()=>dialog.current.close();
 return <>
  <button ref={trigger} type="button" className="button ghost" aria-haspopup="dialog" aria-controls="value-announcement" onClick={open}>阅读公告</button>
  {createPortal(<dialog ref={dialog} id="value-announcement" className="value-announcement-dialog" aria-labelledby="value-announcement-heading" onClose={()=>trigger.current?.focus()}>
   <header className="va-header"><h2 id="value-announcement-heading">阅读公告</h2><button type="button" className="va-close" aria-label="关闭阅读公告" onClick={close}>×</button></header>
   <div className="va-body" tabIndex={0} aria-label="公告正文"><article dangerouslySetInnerHTML={{__html:article}}/></div>
  </dialog>,document.body)}
 </>;
}
