import React, {useEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {noticeCases, noticeGroups} from './securityNoticeCases.mjs';
import './securityNotice.css';

// This version is independent of the design preview and of task/security state.
const seenKey = 'agentscope-security-notice-v2-seen';
function hasSeenNotice() {
  try { return localStorage.getItem(seenKey) === 'true'; } catch { return false; }
}

export default function SecurityNotice() {
  const dialog = useRef(null);
  const trigger = useRef(null);
  const [seen, setSeen] = useState(hasSeenNotice);
  const [group, setGroup] = useState('execution');
  const [selection, setSelection] = useState({execution:'plugin', governance:'isolation'});
  const scene = noticeCases.find(item=>item.id===selection[group]);

  useEffect(()=>{
    if (!hasSeenNotice() && !dialog.current.open) dialog.current.showModal();
  }, []);

  const openNotice = () => { if (!dialog.current.open) dialog.current.showModal(); };
  const closeNotice = () => {
    try { localStorage.setItem(seenKey, 'true'); } catch { /* Still usable when storage is unavailable. */ }
    setSeen(true);
    dialog.current.close();
    trigger.current?.focus();
  };
  const selectScene = id => {
    setSelection(current=>({...current,[group]:id}));
    dialog.current.scrollTop=0;
  };
  const selectGroup = id => { setGroup(id); dialog.current.scrollTop=0; };
  const trapFocus = event => {
    if (event.key!=='Tab') return;
    const controls = [...dialog.current.querySelectorAll('button, summary')].filter(element=>!element.disabled && element.getClientRects().length);
    const first=controls[0], last=controls[controls.length-1];
    if (event.shiftKey && document.activeElement===first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement===last) { event.preventDefault(); first.focus(); }
  };

  return <>
    <button ref={trigger} type="button" className="security-notice-trigger" aria-haspopup="dialog" aria-controls="security-notice" onClick={openNotice}>
      <span aria-hidden="true">◈</span>安全亮点{!seen&&<span className="sn-unread-dot" aria-label="新公告"/>}
    </button>
    {createPortal(<dialog ref={dialog} id="security-notice" className="security-notice-dialog" aria-labelledby="security-notice-heading" onCancel={event=>{event.preventDefault();closeNotice();}} onKeyDown={trapFocus}>
      <header className="sn-notice-header">
        <div className="sn-notice-title"><span className="sn-notice-mark" aria-hidden="true">◈</span><h2 id="security-notice-heading">安全亮点</h2><span className="sn-case-count">{noticeCases.length} 个案例</span></div>
        <button type="button" className="sn-close-button" aria-label="关闭公告" onClick={closeNotice}>×</button>
      </header>
      <div className="sn-notice-layout">
        <nav className="sn-scenario-nav" aria-label="选择安全场景">
          <div className="sn-scenario-groups" aria-label="场景分类">{noticeGroups.map(item=><button key={item.id} type="button" data-group={item.id} aria-pressed={group===item.id} aria-controls="security-notice-buttons" onClick={()=>selectGroup(item.id)}>{item.label}</button>)}</div>
          <div id="security-notice-buttons" className="sn-scenario-buttons">{noticeCases.filter(item=>item.group===group).map((item,index)=><button type="button" className="sn-scenario-button" key={item.id} data-case={item.id} aria-current={scene.id===item.id} aria-controls="security-notice-content" onClick={()=>selectScene(item.id)}><span className="sn-scenario-number">{String(index+1).padStart(2,'0')}</span><span>{item.label}</span></button>)}</div>
          <div className="sn-sample-note">从用户任务到系统行为，<br/>看清每一步如何受约束。</div>
        </nav>
        <article id="security-notice-content" className="sn-scenario-content" aria-live="polite">
          <h3 className="sn-scene-heading">{scene.title}</h3>
          <p className="sn-scene-task"><strong>{scene.actor}</strong>　{scene.task}</p>
          <div className="sn-trace-grid">
            <section className="sn-trace-panel" aria-label={scene.leftTitle}>
              <header className="sn-trace-header"><h3>{scene.leftTitle}</h3><span>{scene.leftKind}</span></header>
              <div className="sn-tool-trace">{scene.leftSteps.map((step,index)=><div className="sn-trace-step" key={index}><span className="sn-time">{step[0]}</span><div><div className="sn-step-title"><span className={scene.isToolTrace&&index===0?'sn-tool-name':''}>{step[1]}</span>{scene.isToolTrace&&index===0&&<span>call_a12</span>}</div><pre className={'sn-code-box'+(index===1?' sn-output':'')}>{step[2]}</pre></div></div>)}</div>
              <p className="sn-tool-insight">{scene.toolNote}</p>
            </section>
            <section className="sn-trace-panel" aria-label={scene.rightTitle}>
              <header className="sn-trace-header"><h3>{scene.rightTitle}</h3><span>{scene.rightKind}</span></header>
              <div className="sn-system-trace">{scene.events.map((event,index)=><div className={'sn-system-event'+(event[5]?' sn-'+event[5]:'')} key={index}><span className="sn-time">+{Number(event[0])}ms</span><div><div className="sn-event-source"><span>{event[1]}</span><strong>{event[2]}</strong>{event[5]&&<span className="sn-verdict">{event[6]||(scene.id==='approval'?'未批准':'拒绝')}</span>}</div><pre className="sn-event-code">{event[3]}</pre>{event[5]&&<div className="sn-event-detail">{event[4]}</div>}</div></div>)}</div>
            </section>
          </div>
          <div className="sn-correlation" aria-label="行为关联">{scene.relation.map((item,index)=><React.Fragment key={index}>{index>0&&<span className="sn-link-arrow">→</span>}<code>{item}</code></React.Fragment>)}</div>
          <div className="sn-value-line"><strong>新增价值</strong><span>{scene.value}</span></div>
          <details className="sn-evidence-details" key={scene.id}><summary>案例过程</summary><div className="sn-case-objects"><span>涉及对象</span>{scene.files.map(file=><code key={file}>{file}</code>)}</div><ol className="sn-case-story">{scene.story.map((step,index)=><li key={index}>{step}</li>)}</ol><p className="sn-case-result"><strong>结果</strong>　{scene.result}</p></details>
        </article>
      </div>
      <footer className="sn-notice-footer"><span>可随时从首页「安全亮点」再次打开。</span><button type="button" className="sn-primary-button" onClick={closeNotice}>知道了</button></footer>
    </dialog>, document.body)}
  </>;
}
