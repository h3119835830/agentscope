import React from 'react';

// Common policy fields across generation, approval and session projections.
export default function PolicyRecordHead({status=false,selection}){
 return <thead><tr>{selection}<th scope="col">策略名称</th><th scope="col">默认动作</th><th scope="col">来源</th>{status&&<th scope="col">状态</th>}<th scope="col" aria-label="操作"/></tr></thead>;
}
