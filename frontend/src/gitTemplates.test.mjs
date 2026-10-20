import test from 'node:test';
import assert from 'node:assert/strict';
import {configurationRecordActions,configurationRecordSummary} from './policyConfigurationPresentation.mjs';

test('unsupported Git parameter draft cannot offer submit or disable',()=>{
 const row={scope:'agent',can_submit:false,status:'draft',parameters:{repository:'/w/0'},execution_support:{applicable:false}};
 assert.equal(configurationRecordActions(row).canSubmit,false);
 assert.equal(configurationRecordActions(row).canDisable,false);
 assert.match(configurationRecordActions(row).submitReason,/ActPlane 暂不支持/);
 assert.equal(configurationRecordSummary(row).status,'暂不支持 · 参数草案');
});

test('Git saved parameters and effect take precedence over newer template defaults',()=>{
 const template={parameters:[{key:'program',label:'Git 程序',type:'program'},{key:'exit_code',label:'成功退出码',type:'integer'},{key:'effect',type:'effect'}],effect:'kill'};
 const row={scope:'system',can_submit:true,status:'draft',parameters:{program:'git',exit_code:0,effect:'notify'},effect:'notify',effective_operations:['exec']};
 const summary=configurationRecordSummary(row,template);
 assert.deepEqual(summary.effects,['notify']);
 assert.match(summary.targetTitle,/成功退出码：0/);
 assert.equal(configurationRecordActions(row).canSubmit,true);
});


test('retired applied configuration stays read-only but can request approved disable',()=>{
 const row={scope:'agent',can_submit:false,read_only:true,status:'draft',revision:1,applied_revision:1,applied:true,execution_support:{applicable:false,status:'legacy'}};
 assert.equal(configurationRecordActions(row).canSubmit,false);
 assert.match(configurationRecordActions(row).submitReason,/历史模板/);
 assert.equal(configurationRecordActions(row).canDisable,true);
 assert.equal(configurationRecordSummary(row).status,'已应用 · 历史配置');
});
test('retired unused configuration cannot request disable and pending disable stays separate',()=>{
 const row={scope:'agent',can_submit:false,read_only:true,status:'draft',execution_support:{applicable:false,status:'legacy'}};
 assert.equal(configurationRecordActions(row).canDisable,false);
 assert.equal(configurationRecordSummary(row).status,'历史配置 · 只读');
 assert.equal(configurationRecordActions({...row,applied_revision:1,status:'pending'}).canDisable,false);
});
