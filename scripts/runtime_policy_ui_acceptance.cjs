// Browser acceptance against real read-only isolated API data. No mocks or DOM edits.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
 const out=process.argv[2];await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:720}}),requests=[];
  page.on('request',request=>{if(request.url().includes('/api/'))requests.push({url:request.url(),method:request.method()})});
  const url=task=>'http://127.0.0.1:18006/?task='+task;
  await page.goto(url('c7ae28357e224c7d'),{waitUntil:'networkidle'});
  const name=page.getByRole('button',{name:/保护 memory-note.txt/});await name.waitFor();
  assert.deepEqual(await page.locator('.runtime-policies th').allTextContents(),['策略名称','由谁触发']);
  assert.equal(await page.locator('.runtime-policies tbody tr').count(),1);
  assert.doesNotMatch(await page.locator('body').innerText(),/核验|Hook|PID|生成作业|次评估|策略 v|跨会话持久记忆加载/);
  await page.locator('.runtime-policy-page').screenshot({path:path.join(out,'runtime-list.png')});
  await name.click();await page.getByText('具体约束',{exact:true}).waitFor();
  assert.deepEqual(await page.locator('.runtime-policy-details dt').allTextContents(),['具体约束','作用对象','参考模板','触发原文']);
  assert.match(await page.locator('.runtime-policy-details').innerText(),/已检索已审核模板，未引用具体模板/);
  assert.match(await page.locator('.runtime-policy-details').innerText(),/我增加约束：从现在起必须保护 memory-note.txt/);
  assert.equal(await page.locator('.runtime-policy-dsl').getAttribute('open'),null);
  assert.equal(await page.locator('.runtime-policy-dsl pre').isVisible(),false);
  await page.locator('.runtime-policy-page').screenshot({path:path.join(out,'runtime-detail.png')});
  await page.getByText('查看 DSL',{exact:true}).click();
  const dsl=await page.locator('.runtime-policy-dsl pre').innerText();assert.match(dsl,/block write file/);assert.match(dsl,/block unlink file/);assert.doesNotMatch(dsl,/project_a\/main.py/);
  await name.click();assert.equal(await page.locator('.runtime-policy-details').count(),0);
  await page.goto(url('dad7f1c9dacb4f4c'),{waitUntil:'networkidle'});await page.getByText('暂未生成新的运行时策略。',{exact:true}).waitFor();
  assert.equal(await page.locator('.runtime-policy-name').count(),0);
  await page.goto(url('c7ae28357e224c7d'),{waitUntil:'networkidle'});await name.waitFor();
  await page.setViewportSize({width:375,height:720});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await name.click();await page.getByText('具体约束',{exact:true}).waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('.runtime-policy-page').screenshot({path:path.join(out,'runtime-mobile.png')});
  assert.ok(requests.every(request=>request.method==='GET'));
  assert.ok(requests.some(request=>request.url.includes('generated_only=true')));
  const result={result:'PASS',checks:['two_columns_only','only_generated_policy','diagnostics_hidden','details_on_demand','actual_template_provenance','exact_trigger_text','dsl_folded_by_default','exact_dsl_only','collapse_clears_details','different_task_isolation','mobile_no_overflow','get_only_requests','server_side_generated_filter'],requests};
  await fs.writeFile(path.join(out,'browser-acceptance.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({result:result.result,checks:result.checks,screenshots:out}));
 }finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1});
