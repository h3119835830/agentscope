// Server projections are the only product-state source. Legacy active/gate
// fields remain for compatibility, never for deciding a green status.
export function currentStatus(value,dimension='loading',now=Date.now(),failed=false){
 const fallback=dimension==='loading'?{state:'unverified',label:'未核验'}:{state:'unknown',label:'状态未知'};
 const allowed=dimension==='loading'?['loaded','checking','unverified','stopped','observed']:['running','paused','starting','stopped','failed','unknown'];
 if(failed||!value||!allowed.includes(value.state))return fallback;
 const expiring=dimension==='loading'?['loaded','checking'].includes(value.state):!['stopped','failed'].includes(value.state);
 if(expiring&&(!value.expires_at||!Number.isFinite(Date.parse(value.expires_at))||now>=Date.parse(value.expires_at)))return {...value,...fallback,expired:true};
 return value;
}
export function currentLoadedView(view,now=Date.now(),failed=false){
 if(!view)return null;
 const status=currentStatus(view.loading_status,'loading',now,failed);
 if(status.state==='loaded')return view;
 return {...view,records:[],coverage_complete:false,
  state:status.state==='observed'?'observed':'unverified',
  message:status.state==='stopped'?'Agent 未运行，历史加载记录不计入当前清单。':
   status.state==='observed'?view.message:'当前加载证据未核验或已过期，请刷新重试。',
  loading_status:status};
}
export function invalidateAgent(row){
 return {...row,connected:false,active:false,status:'unknown',can_open:false,
  product_status:{...row.product_status,
   runtime:currentStatus(null,'runtime'),loading:currentStatus(null)}};
}
