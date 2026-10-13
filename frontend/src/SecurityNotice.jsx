import React,{useId,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {valueCases,evidenceFor} from './securityValueCases.mjs';
import {sceneGroups,storyFor} from './securitySceneStories.mjs';
import evidence from './valueEvidence.json';
import './securityNotice.css';

export default function SecurityNotice(){
 const dialog=useRef(null),trigger=useRef(null),heading=useRef(null),body=useRef(null);
 const instance=useId(),dialogId='security-notice-'+instance,headingId=dialogId+'-heading';
 const [selected,setSelected]=useState('plugin');
 const scene=valueCases.find(item=>item.id===selected),state=scene&&evidenceFor(scene,evidence);
 const story=scene&&storyFor(scene,state);
 const open=()=>{setSelected('plugin');if(!dialog.current.open)dialog.current.showModal();if(body.current)body.current.scrollTop=0;requestAnimationFrame(()=>heading.current?.focus());};
 const close=()=>{dialog.current.close();trigger.current?.focus();};
 const select=id=>{setSelected(id);if(body.current)body.current.scrollTop=0;requestAnimationFrame(()=>heading.current?.focus());};
 return <>
 <div className="security-notice-actions"><button ref={trigger} type="button" className="security-notice-trigger" aria-haspopup="dialog" aria-controls={dialogId} onClick={open}><span aria-hidden="true">◈</span>安全总览</button><a className="sn-announcement-link" href="/value-announcement.html" target="_blank" rel="noreferrer">阅读公告 <span aria-hidden="true">↗</span></a></div>
 {createPortal(<dialog ref={dialog} id={dialogId} className="security-notice-dialog sn-guide-dialog" aria-labelledby={headingId} onCancel={event=>{event.preventDefault();close();}}>
  <header className="sn-notice-header"><div className="sn-notice-title"><span className="sn-notice-mark" aria-hidden="true">◈</span><h2 id={headingId}>安全总览</h2><span className="sn-header-caption">从工具调用，看到真实系统行为</span></div><div className="sn-header-actions"><a href="/value-announcement.html" target="_blank" rel="noreferrer">阅读公告 ↗</a><button type="button" className="sn-close-button" aria-label="关闭安全总览" onClick={close}>×</button></div></header>
  <div className="sn-guide-layout">
   <nav className="sn-guide-nav" aria-label="安全场景">{sceneGroups.map(group=><div className="sn-nav-group" key={group.label}><p>{group.label}</p>{group.ids.map(id=>{const item=valueCases.find(c=>c.id===id),itemState=evidenceFor(item,evidence),itemStory=storyFor(item,itemState);return <button key={id} type="button" aria-current={selected===id?'page':undefined} onClick={()=>select(id)}><span>{itemStory.short}</span><span aria-hidden="true">›</span></button>;})}</div>)}<button type="button" className="sn-all-scenes" aria-current={!scene?'page':undefined} onClick={()=>select(null)}>全部 12 类场景与结论</button></nav>
   <div ref={body} className="sn-value-body">
   <div className="sn-mobile-selector"><label htmlFor={dialogId+'-select'}>选择场景</label><select id={dialogId+'-select'} value={selected||''} onChange={event=>select(event.target.value||null)}>{valueCases.map(item=><option key={item.id} value={item.id}>{storyFor(item,evidenceFor(item,evidence)).short}</option>)}<option value="">全部 12 类场景与结论</option></select></div>
   {!scene?<>
    <h3 ref={heading} tabIndex={-1} className="sn-scene-heading">12 类场景与验证结论</h3><p className="sn-intro">先选择一个具体任务，看它怎样越界、哪里被约束，再按需查看依据。</p>
    <p className="sn-history-note">本机验证、机制依据和后续设计分别标识。当前 Agent 的保护请看总览核验时间。</p>
    <div className="sn-catalog-scroll"><table className="sn-catalog"><caption className="sr-only">保护对象、攻击路径与验证结论</caption><thead><tr><th>场景与保护对象</th><th>攻击路径</th><th>验证结论</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{valueCases.map(item=>{const itemState=evidenceFor(item,evidence);return <tr key={item.id}><td><b>{item.label}</b><small>{item.object}</small></td><td>{item.path}</td><td><span className={'sn-proof '+itemState.tone}>{itemState.label}</span></td><td><button type="button" className="sn-detail-button" onClick={()=>select(item.id)} aria-label={'查看'+item.label}>看图解</button></td></tr>;})}</tbody></table></div>
   </>:<>
    <div className="sn-scene-kicker"><span>{story.measured?'实测结果图解':'机制说明与后续设计'}</span><span className={'sn-proof '+state.tone}>{state.label}</span></div>
    <h3 ref={heading} tabIndex={-1} className="sn-scene-heading">{story.title}</h3>
    <p className="sn-task"><strong>你允许的任务</strong>{scene.task}</p>
    <div className="sn-visual-comparison">
     <section className="sn-tool-panel" aria-label="工具层能看到"><h4><span aria-hidden="true">⌘</span>工具层能看到</h4><div className="sn-tool-content">{story.tool.map((text,index)=><div className="sn-tool-row" key={text}><span>{index===0?'入口':'后续'}</span><p>{text}</p></div>)}</div><p className="sn-tool-insight">{story.insight}</p></section>
     <section className="sn-system-panel" aria-label={story.measured?'系统实际约束的行为':'需要建立的保护链'}><h4><span aria-hidden="true">◈</span>{story.measured?'系统实际约束的行为':'需要建立的保护链'}</h4><ol className="sn-behavior-flow">{story.steps.map((step,index)=><li key={index} className={'sn-behavior '+step.tone}><span className="sn-flow-dot" aria-hidden="true"/><div><div className="sn-behavior-title"><b>{step.title}</b><span>{step.label}</span></div><p>{step.detail}</p></div></li>)}</ol></section>
    </div>
    <div className="sn-value-line"><span aria-hidden="true">↳</span><p>{story.takeaway}</p></div>
    <p className="sn-proof-note">{state.proof?`按 ${evidence.date} 本机实验整理，重复 ${state.proof.repetitions} 次；图解不是原始调用记录。`:'本场景尚无本轮完整实证，图解说明预期机制。'} 当前保护以首页核验时间为准。</p>
    <details className="sn-references" key={scene.id}><summary>已有防护、适用边界与实验依据</summary><div className="sn-research-details"><h4>已有防护与本轮增量</h4><p>{scene.before}</p><p>{scene.mechanism}</p><h4>验证结果与适用边界</h4>{state.proof&&<><p>{state.proof.result}</p><p>{state.proof.control}</p><small>{evidence.environment}</small></>}<p>{scene.boundary}</p><h4>攻击者能力</h4><p>{scene.attacker}</p><p><a href="https://arxiv.org/html/2606.25189v2" target="_blank" rel="noreferrer">ActPlane 论文 v2</a> · <a href="https://github.com/eunomia-bpf/ActPlane/tree/404542899a2153af0952cbf0dc52aeab0b7c5034" target="_blank" rel="noreferrer">固定提交源码</a>{state.proof&&evidence.reportUrl&&<> · <a href={evidence.reportUrl} target="_blank" rel="noreferrer">本机实验报告</a></>}</p><p>本轮没有复现 CaMeL、Progent、FIDES 的完整系统。阅读图解不会改变策略。</p></div></details>
   </>}
   </div>
  </div>
  <footer className="sn-notice-footer"><span>阅读图解不改变策略，配置与扩权仍需人工确认。</span><button type="button" className="sn-primary-button" onClick={close}>返回总览</button></footer>
 </dialog>,document.body)}
 </>;
}
