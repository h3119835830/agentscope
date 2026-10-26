import test from 'node:test';
import assert from 'node:assert/strict';
import {approvalDslDocuments} from './approvalDsl.mjs';

const own={id:'own',name:'报告约束',original_dsl:'rule report:\n block write file "/w/0/report.md" if AGENT unless lineage-includes exec "python3"'};
const other={id:'other',name:'其他已应用策略',original_dsl:'rule other:\n block exec "sudo" if AGENT'};
test('DSL belongs to the exact selected approval and excludes retained policies',()=>{
 const row={approval_unit:{configuration_id:'own',revision:1,operation:'apply'},documents:[other,own]};
 assert.deepEqual(approvalDslDocuments(row),[{id:'own',name:own.name,text:own.original_dsl,removal:false}]);
});
test('withdrawal and edited candidates display their frozen approved configuration DSL',()=>{
 for(const operation of ['apply','disable']){
  const row={approval_unit:{configuration_id:'own',revision:1,operation},configuration_records:[{id:'own',revision:1,document:own}],documents:[other,{...own,original_dsl:'different version'}]};
  assert.equal(approvalDslDocuments(row)[0].text,own.original_dsl);
  assert.equal(approvalDslDocuments(row)[0].removal,operation==='disable');
 }
});
test('missing exact policy DSL cannot fall back to a sibling or newer version',()=>{
 const row={approval_unit:{configuration_id:'own',revision:1,operation:'disable'},configuration_records:[{id:'own',revision:2,document:own}],documents:[other]};
 assert.deepEqual(approvalDslDocuments(row),[]);
});
test('revalidation shows the proposed DSL and marks explicit removals',()=>{
 const plan={comparisons:[{name:'更新',before_dsl:'old',after_dsl:'new'},{name:'停用',before_dsl:'removed',removal:true}]};
 assert.deepEqual(approvalDslDocuments({},plan).map(d=>[d.text,d.removal]),[['new',false],['removed',true]]);
});
