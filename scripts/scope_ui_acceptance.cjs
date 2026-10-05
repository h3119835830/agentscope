/* Browser acceptance; reads credentials into memory only and exports no credential value. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const task=process.argv[2];
const output=process.argv[3];
const secret=spawnSync('wsl.exe',['-d','Ubuntu','-u','root','--','/opt/agentscope/.venv/bin/python','-c',
  'import sys; sys.path.insert(0,"/opt/agentscope-history-v1/scripts"); from scope_service import environment; print(environment()["AGENTSCOPE_ADMIN_TOKEN"])'],
  {encoding:'utf8',windowsHide:true});
if(secret.status!==0)throw new Error('Could not read local test credential');
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.addInitScript(({token,task})=>{
    sessionStorage.setItem('agentscopeAdminToken',token);
    localStorage.setItem('scopeDemoTask',task);
  },{token:secret.stdout.trim(),task});
  const page=await context.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18003/?view=scope-demo');
  await page.getByRole('tab',{name:'当前权限',exact:true}).waitFor();
  await page.getByRole('heading',{name:/当前有效权限|已结束的权限记录/}).waitFor();
  assert.equal(await page.locator('.scope-workbench table tbody tr').count(),6);
  await page.screenshot({path:path.join(output,'scope-desktop.png'),fullPage:true});
  await page.getByRole('tab',{name:'当前权限',exact:true}).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('tab',{name:/变更审核/}).getAttribute('aria-selected'),'true');
  await page.getByRole('tabpanel',{name:/变更审核/}).waitFor();
  await page.getByRole('tab',{name:/变更审核/}).focus();
  await page.keyboard.press('ArrowRight');
  await page.getByRole('heading',{name:'权限与执行时间线'}).waitFor();
  await page.getByRole('tab',{name:'当前权限',exact:true}).click();
  await page.locator('.scope-pane').getByRole('button',{name:'详情',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'visible'});
  await page.keyboard.press('Escape');
  await page.getByRole('dialog').waitFor({state:'hidden'});
  assert.equal(await page.evaluate(()=>document.activeElement.textContent),'详情');
  await page.reload();
  await page.getByRole('heading',{name:/当前有效权限|已结束的权限记录/}).waitFor();
  assert.equal(await page.getByLabel('选择 Demo 任务').inputValue(),task);
  await page.setViewportSize({width:423,height:900});
  await page.locator('.shell.sidebar-collapsed').waitFor();
  await page.screenshot({path:path.join(output,'scope-narrow.png'),fullPage:true});
  const size=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));
  assert.ok(size.document<=size.viewport,JSON.stringify(size));
  await page.getByRole('tab',{name:/变更审核/}).click();
  await page.screenshot({path:path.join(output,'scope-review-narrow.png'),fullPage:true});
  assert.equal(errors.length,0,errors.join(';'));
  const result={task,desktop:'passed',narrow423:'passed',tabs:'passed',keyboard:'passed',dialogFocus:'passed',refresh:'passed',pageErrors:errors};
  fs.writeFileSync(path.join(output,'scope-ui.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
  await browser.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
