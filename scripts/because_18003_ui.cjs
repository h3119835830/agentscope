/* Shared real API: preserve existing configurations, archive only our own draft. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=process.argv[2],url='http://127.0.0.1:18003';
(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const page=await context.newPage();page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const read=async route=>{const r=await context.request.get(url+route);assert.ok(r.ok());return r.json();};
 const post=async(route,body)=>{const r=await context.request.post(url+route,{data:body});assert.ok(r.ok(),await r.text());return r.json();};
 const base='/api/security/system/policy-library';let owned=null;
 try{
  const before=await read(base),agents=(await read('/api/agent-instances')).instances;
  assert.equal(before.catalog.length,12);
  await page.goto(url+'/?view=strategies&systemTab=policies');
  await page.getByRole('table',{name:'系统策略配置库'}).waitFor();
  const checks=[];
  for(const preset of before.catalog){
   await page.getByRole('button',{name:preset.name,exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'配置系统策略'});
   const saved=before.items.find(i=>i.config?.template_id===preset.id);
   assert.equal(await dialog.getByLabel('反馈原因',{exact:true}).inputValue(),saved?saved.config.reason:preset.reason);
   await dialog.getByText('适用条件与来源',{exact:true}).click();
   assert.doesNotMatch(await dialog.innerText(),/RQ1\b/i);
   checks.push({id:preset.id,default_or_existing_feedback_verified:true,existing_preserved:!!saved});
   if(!saved&&checks.length===2)await page.screenshot({path:path.join(output,'default-feedback-18003.png'),fullPage:true});
   await dialog.getByRole('button',{name:'取消',exact:true}).click();
  }
  // Owned draft round trip; no proposal or confirmation endpoint is called.
  const config=Object.fromEntries(['name','mode','values','ops','effect','reason'].map(k=>[k,before.catalog[0][k]]));
  Object.assign(config,{template_id:before.catalog[0].id,name:'反馈验收临时配置 20261011',reason:before.catalog[0].reason+' 请记录公开验证结果。'});
  owned=await post(base,{kind:'structured',config,base_revision:0});
  const saved=await read(base);owned=saved.items.find(i=>i.name===config.name);assert.ok(owned&&!owned.applied);
  await page.reload();await page.getByRole('button',{name:config.name,exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'配置系统策略'});
  assert.equal(await dialog.getByLabel('反馈原因',{exact:true}).inputValue(),config.reason);
  await dialog.getByRole('tab',{name:'原始 DSL',exact:true}).click();assert.ok((await dialog.innerText()).includes(config.reason));
  await dialog.getByRole('button',{name:'取消',exact:true}).click();
  await post(base+'/'+owned.id+'/archive',{revision:owned.revision});owned=null;
  const after=await read(base);
  assert.deepEqual(after.items,before.items);assert.equal(after.base_hash,before.base_hash);assert.equal(after.base_revision,before.base_revision);
  await page.goto(url+'/?view=strategies&systemTab=templates');
  const table=page.getByRole('table',{name:'策略模板记录'});await table.waitFor();
  assert.doesNotMatch(await table.innerText(),/RQ1\b|编号/i);
  await page.screenshot({path:path.join(output,'templates-18003.png'),fullPage:true});
  const names=await table.locator('.policy-record-title').allTextContents();assert.equal(names.length,6);
  const active=agents.find(a=>a.mode==='controlled'&&a.active&&a.agent_type==='dsh');assert.ok(active);
  const templates=[];
  for(const name of names){
   await page.getByRole('button',{name,exact:true}).click();dialog=page.getByRole('dialog',{name:'配置详情 · '+name});
   await dialog.getByLabel('模板目标 Agent').selectOption(active.id);
   await dialog.getByText('补充说明',{exact:true}).click();assert.doesNotMatch(await dialog.innerText(),/RQ1\b/i);
   await dialog.getByRole('tab',{name:'DSL 预览',exact:true}).click();assert.doesNotMatch(await dialog.innerText(),/RQ1\b/i);
   assert.ok((await dialog.innerText()).includes('because'));
   templates.push({name,details_without_research_ids:true,dsl_without_research_ids:true});
   await dialog.getByRole('button',{name:'取消',exact:true}).click();
  }
  await page.setViewportSize({width:423,height:900});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(output,'templates-18003-423.png'),fullPage:true});
  await page.setViewportSize({width:1440,height:1000});
  await page.goto(url+'/?view=approvals');await page.getByRole('table',{name:'策略审批记录'}).waitFor();
  assert.ok((await page.locator('body').innerText()).includes('生成会话'));
  await page.screenshot({path:path.join(output,'approval-locations-preserved.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,'ui-acceptance.json'),JSON.stringify({passed:true,url,checks,templates,
   existing_configurations_unchanged:true,custom_round_trip:true,no_policy_application:true,narrow423:true,
   approval_locations_preserved:true,page_errors:errors,base_revision:after.base_revision,base_hash:after.base_hash},null,2));
  console.log(JSON.stringify({passed:true,defaults:checks.length,templates:templates.length,no_policy_application:true}));
 }catch(e){await page.screenshot({path:path.join(output,'ui-failure.png'),fullPage:true});throw e;}
 finally{if(owned)await post(base+'/'+owned.id+'/archive',{revision:owned.revision});await browser.close();}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
