import test from 'node:test';
import assert from 'node:assert/strict';
import {valueCases,evidenceFor} from './securityValueCases.mjs';

test('missing evidence cannot become a verified result or a current protection claim',()=>{
 for(const scene of valueCases){assert.ok(scene.task&&scene.attacker&&scene.before&&scene.mechanism&&scene.boundary);assert.equal(evidenceFor(scene,{}).proof,null);}
 assert.equal(valueCases.length,12);assert.equal(new Set(valueCases.map(c=>c.id)).size,12);
});
test('same destination comparison reuses its experiment, and a failed report remains pending',()=>{
 const scene=valueCases.find(c=>c.id==='destination');
 assert.equal(evidenceFor(scene,{scenarios:{flow:{verified:false}}}).proof,null);
 const proof={verified:true,repetitions:3};assert.equal(evidenceFor(scene,{scenarios:{flow:proof}}).proof,proof);
 assert.equal(valueCases.find(c=>c.id==='business').level,'negative');
});
