// Real system-route acceptance; no mocked data, writes, or native task startup.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
 const [out,port='18005',task='c7ae28357e224c7d']=process.argv.slice(2);await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'}),requests=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('request',r=>{if(r.url().includes('/api/'))requests.push({url:r.url(),method:r.method()})});
  if(port==='18005'){
   await page.goto(`http://127.0.0.1:${port}/?view=workbench&task=${task}&agentPolicyTab=runtime`,{waitUntil:'domcontentloaded'});
   await page.getByRole('button',{name:'详情',exact:true}).waitFor();
   assert.deepEqual(await page.locator('.runtime-policies th').allTextContents(),['策略名称','默认动作','来源','状态','']);
   assert.equal(await page.locator('.runtime-policies tbody tr td').nth(1).innerText(),'阻断');
   await page.screenshot({path:path.join(out,'system-runtime-record.png'),fullPage:true});
   await page.getByRole('button',{name:'详情',exact:true}).click();await page.getByText('具体约束',{exact:true}).waitFor();
   assert.equal(await page.getByText('作用对象',{exact:true}).count(),0);
   await page.getByText('查看 DSL',{exact:true}).click();assert.match(await page.locator('.runtime-policy-dsl pre').innerText(),/block unlink file/);
   await page.screenshot({path:path.join(out,'system-runtime-dsl.png'),fullPage:true});
   await page.goto(`http://127.0.0.1:${port}/?view=history&archive=${task}&archivePane=runtime`,{waitUntil:'domcontentloaded'});
   await page.getByRole('button',{name:'详情',exact:true}).waitFor();assert.equal(await page.getByText('Hook 触发点',{exact:true}).count(),0);
  }else{
   await page.goto(`http://127.0.0.1:${port}/?view=workbench&policyAgent=instance-1f4469579e8947f4&agentPolicyTab=runtime`,{waitUntil:'domcontentloaded'});
   await page.getByRole('tab',{name:'运行时策略',exact:true}).waitFor();await page.locator('.runtime-policies th').first().waitFor();
   assert.deepEqual(await page.locator('.runtime-policies th').allTextContents(),['策略名称','默认动作','来源','状态','']);
   assert.equal(await page.getByText('工具运行事件',{exact:true}).count(),0);
   await page.screenshot({path:path.join(out,'installed-runtime-page.png'),fullPage:true});
   await page.getByRole('tab',{name:'策略助手',exact:true}).click();await page.locator('.policy-assistant').first().waitFor();
   assert.equal(await page.locator('.runtime-policies').count(),0);
   await page.getByRole('tab',{name:'运行时策略',exact:true}).click();await page.locator('.runtime-policies th').first().waitFor();
  }
  assert.ok(requests.every(r=>r.method==='GET'));
  await fs.writeFile(path.join(out,'system-ui-'+port+'.json'),JSON.stringify({result:'PASS',port,requests},null,2));console.log(JSON.stringify({result:'PASS',port,requests:requests.length}));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
