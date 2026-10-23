// Navigation metadata only. Template definitions remain server-owned.
export const PRIMARY_TYPES = [
  {value:'file',label:'文件与目录操作'},
  {value:'exec',label:'程序与命令执行'},
  {value:'network',label:'网络连接'},
];

const OPERATION_TYPES = {
  open:'file',read:'file',write:'file',unlink:'file',
  exec:'exec',connect:'network',recv:'network',
};

export function primaryType(template){
  if(!template||template.custom)return '';
  return OPERATION_TYPES[template.operation]||'';
}

export function primaryTypeLabel(template){
  return PRIMARY_TYPES.find(type=>type.value===primaryType(template))?.label||'自定义策略 · 操作见详情';
}

export function templateFacets(template){
  if(!template||template.custom)return [];
  const facets=[];
  if(template.id?.startsWith('SYS-'))facets.push('系统预设');
  if(template.id?.startsWith('GIT-')||template.id==='RQ1-GIT')facets.push('Git');
  if(template.execution_support?.event_type==='跨事件'||['lineage','flow','remote','workflow','git-check'].includes(template.renderer))facets.push('跨事件');
  if(template.category==='生成产物')facets.push('生成产物');
  if(template.category?.includes('凭据保护'))facets.push('凭据');
  return facets;
}
