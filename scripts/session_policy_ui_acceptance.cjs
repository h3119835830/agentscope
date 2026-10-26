// Real installed UI, GET-only. No synthetic rows or policy mutations.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
 const [out]=process.argv.slice(2);await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'}),requests=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('request',r=>{if(r.url().includes('/api/'))requests.push({url:r.url(),method:r.method()})});
  const root='http://127.0.0.1:18003',instance='instance-1f4469579e8947f4',session='session-cf4f111b-d72b-45da-b698-bea94c34a4ed';
  await page.goto(root+'/?view=sessions&sessionInstance='+instance+'&sessionId='+session+'&sessionTab=policies',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'← 返回会话目录',exact:true}).waitFor();
  assert.equal(await page.locator('.session-workbench-directory,.session-directory-toggle').count(),0);
  const response=await page.request.get(root+'/api/console/agents/'+instance+'/sessions/'+session+'/policies');assert.equal(response.status(),200);
  const data=await response.json();assert.ok(data.policy_records);assert.ok(data.policy_records.records.length>0,'real inherited load record required');
  assert.ok(data.policy_records.records.every(r=>r.stage==='startup'||r.stage==='runtime'));
  assert.deepEqual(await page.locator('.session-security-panel th').allTextContents(),['策略名称','默认动作','来源','状态','']);
  assert.equal(await page.getByText('策略名称／对象',{exact:true}).count(),0);
  await page.screenshot({path:path.join(out,'session-policies.png'),fullPage:true});
  await page.getByRole('button',{name:'详情',exact:true}).first().click();await page.getByRole('dialog',{name:'已加载策略详情'}).waitFor();
  const dsl=page.getByText('查看 DSL',{exact:true});assert.equal(await page.locator('.runtime-policy-dsl').getAttribute('open'),null);await dsl.click();assert.ok((await page.locator('.runtime-policy-dsl pre').innerText()).length>0);
  await page.screenshot({path:path.join(out,'session-policy-detail.png'),fullPage:true});await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.getByLabel('筛选策略来源').selectOption('runtime');assert.equal(await page.locator('.session-security-panel tbody tr').count(),data.policy_records.records.filter(r=>r.stage==='runtime').length);
  await page.getByLabel('筛选策略来源').selectOption('startup');
  await page.setViewportSize({width:600,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:path.join(out,'session-mobile.png'),fullPage:true});
  await page.getByRole('button',{name:'← 返回会话目录',exact:true}).click();await page.getByRole('button',{name:'查看策略详情',exact:true}).first().waitFor();
  await page.setViewportSize({width:1440,height:1000});await page.goto(root+'/?view=approvals',{waitUntil:'networkidle'});
  assert.deepEqual((await page.locator('.approval-records th').allTextContents()).slice(-5),['策略名称','默认动作','来源','状态','']);
  await page.getByRole('tab',{name:/已处理/}).click();await page.waitForTimeout(300);
  const runtimeApproval=page.locator('.approval-records tbody tr').filter({hasText:'Agent 运行时执行权限变更'});
  if(await runtimeApproval.count())assert.match(await runtimeApproval.first().locator('[data-label="来源"]').innerText(),/运行时/);
  await page.screenshot({path:path.join(out,'approval-fields.png'),fullPage:true});
  assert.ok(requests.every(r=>r.method==='GET'));
  const result={result:'PASS',checks:['detail_directory_removed','return_directory','real_inherited_snapshot','common_fields','startup_runtime_filter','folded_exact_dsl','mobile_no_page_overflow','approval_common_fields','get_only'],session_record_count:data.policy_records.records.length,requests};
  await fs.writeFile(path.join(out,'session-ui-acceptance.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({result:result.result,checks:result.checks,records:result.session_record_count}));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1});
