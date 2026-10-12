import React,{useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {valueCases,evidenceFor} from './securityValueCases.mjs';
import evidence from './valueEvidence.json';
import './securityNotice.css';

export default function SecurityNotice(){
 const dialog=useRef(null),trigger=useRef(null),heading=useRef(null);
 const [selected,setSelected]=useState(null);
 const scene=valueCases.find(item=>item.id===selected),state=scene&&evidenceFor(scene,evidence);
 const open=()=>{if(!dialog.current.open)dialog.current.showModal();};
 const close=()=>{dialog.current.close();trigger.current?.focus();};
 const select=id=>{setSelected(id);requestAnimationFrame(()=>heading.current?.focus());};
 return <>
 <button ref={trigger} type="button" className="security-notice-trigger" aria-haspopup="dialog" aria-controls="security-notice" onClick={open}><span aria-hidden="true">◈</span>安全亮点 · 12 类场景</button>
 {createPortal(<dialog ref={dialog} id="security-notice" className="security-notice-dialog sn-value-dialog" aria-labelledby="security-notice-heading" onCancel={event=>{event.preventDefault();close();}}>
  <header className="sn-notice-header"><div className="sn-notice-title"><span className="sn-notice-mark" aria-hidden="true">◈</span><h2 id="security-notice-heading">安全亮点</h2></div><button type="button" className="sn-close-button" aria-label="关闭安全亮点" onClick={close}>×</button></header>
  <div className="sn-value-body">
   {!scene?<>
    <p className="sn-intro">允许一个工具，不代表允许它产生的全部效果。这里用具体任务说明 OS 策略能增加什么，以及仍需哪些防护。</p>
    <p className="sn-history-note">实验是历史验证，不能证明当前 Agent 正受保护；当前状态请查看总览中的核验时间。</p>
    <div className="sn-catalog-scroll"><table className="sn-catalog"><caption className="sr-only">保护对象、攻击路径与验证结论</caption><thead><tr><th>场景与保护对象</th><th>攻击路径</th><th>验证结论</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{valueCases.map(item=>{const itemState=evidenceFor(item,evidence);return <tr key={item.id}><td><b>{item.label}</b><small>{item.object}</small></td><td>{item.path}</td><td><span className={'sn-proof '+itemState.tone}>{itemState.label}</span></td><td><button type="button" className="sn-detail-button" onClick={()=>select(item.id)} aria-label={'查看'+item.label}>查看</button></td></tr>;})}</tbody></table></div>
   </>:<>
    <button type="button" className="sn-back" onClick={()=>setSelected(null)}>← 返回场景目录</button>
    <div className="sn-detail-title"><h3 ref={heading} tabIndex={-1}>{scene.label}</h3><span className={'sn-proof '+state.tone}>{state.label}</span></div>
    <dl className="sn-facts"><dt>合法任务</dt><dd>{scene.task}</dd><dt>攻击者能力</dt><dd>{scene.attacker}</dd></dl>
    <div className="sn-attack-chain" aria-label="攻击过程">{scene.chain.map((step,index)=><p key={step}><span aria-hidden="true">{index+1}</span>{step}</p>)}</div>
    <div className="sn-comparison"><section><h4>已有防护能做什么</h4><p>{scene.before}</p></section><section><h4>ActPlane 与 AgentScope 增加什么</h4><p>{scene.mechanism}</p><p className="sn-value-conclusion">{scene.value}</p></section></div>
    <section className="sn-result"><h4>本轮结果</h4>{state.proof?<><p>{state.proof.result}</p><p>{state.proof.control}</p><small>验证日期：{evidence.date} · {evidence.environment} · {state.proof.repetitions} 次重复</small></>:<p>尚无本轮完整实证。这里展示机制依据、攻击配方或延伸方案；未用示意记录冒充实际拦截。</p>}</section>
    <section className="sn-boundary"><h4>适用条件与边界</h4><p>{scene.boundary}</p></section>
    <details className="sn-references"><summary>查看依据</summary><p>机制来源：<a href="https://arxiv.org/html/2606.25189v2" target="_blank" rel="noreferrer">ActPlane 论文 v2</a>；<a href="https://github.com/eunomia-bpf/ActPlane/tree/404542899a2153af0952cbf0dc52aeab0b7c5034" target="_blank" rel="noreferrer">固定提交源码</a>。</p>{state.proof&&<p>本机实验分别核验执行效果、文件完整性与内核拒绝。{evidence.reportUrl?<a href={evidence.reportUrl} target="_blank" rel="noreferrer">查看可复现实验报告</a>:'实验报告尚未随当前版本发布。'}</p>}<p>传统沙箱也能阻止多种文件越界。本轮没有复现 CaMeL、Progent、FIDES 的完整系统。</p></details>
   </>}
  </div>
  <footer className="sn-notice-footer"><span>阅读案例不改变策略。配置与扩权仍需人工确认。</span><button type="button" className="sn-primary-button" onClick={close}>关闭</button></footer>
 </dialog>,document.body)}
 </>;
}
