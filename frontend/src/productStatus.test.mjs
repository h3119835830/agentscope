import test from 'node:test';
import assert from 'node:assert/strict';
import {currentStatus,currentLoadedView,invalidateAgent} from './productStatus.mjs';
import {agentName,entryAction} from './agentInstancePresentation.mjs';
const expiry='2026-10-20T00:00:08Z',before=Date.parse(expiry)-1;
test('only a current server projection is green, exactly until expiry',()=>{
 const s={state:'loaded',label:'已加载',expires_at:expiry};
 assert.equal(currentStatus(s,'loading',before).state,'loaded');
 assert.equal(currentStatus(s,'loading',before+1).state,'unverified');
 assert.equal(currentStatus(s,'loading',before,true).state,'unverified');
 assert.equal(currentStatus({active:true,gate:'open'},'loading',before).state,'unverified');
 assert.equal(currentStatus(null).state,'unverified');
});
test('expired loads and failed requests retain readable rows without retaining green authority',()=>{
 const view={loading_status:{state:'loaded',expires_at:expiry},records:[{name:'v2'}],state:'verified',coverage_complete:true};
 assert.equal(currentLoadedView(view,before).records.length,1);
 assert.deepEqual({records:currentLoadedView(view,before+1).records.length,state:currentLoadedView(view,before+1).state,historical:currentLoadedView(view,before+1).historical},{records:1,state:'unverified',historical:true});
 assert.deepEqual({records:currentLoadedView(view,before,true).records.length,state:currentLoadedView(view,before,true).state,historical:currentLoadedView(view,before,true).historical},{records:1,state:'unverified',historical:true});
 assert.equal(invalidateAgent({product_status:{loading:view.loading_status}}).product_status.loading.state,'unverified');
});
test('same-name inactive agents are distinct and start is explicit',()=>{
 const a={id:'instance-aaaa1111',name:'助手',agent_type:'dsh',mode:'controlled',product_status:{runtime:{state:'stopped'}}};
 const b={...a,id:'instance-bbbb2222'};
 assert.notEqual(agentName(a),agentName(b));
 assert.equal(agentName(a),agentName({...a,pid:999}));
 assert.equal(entryAction(a).label,'启动并打开');
 assert.notEqual(entryAction({...a,product_status:{runtime:{state:'unknown'}}}).action,'start');
});
