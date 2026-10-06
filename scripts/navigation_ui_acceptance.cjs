/* Real read-only UI acceptance: shared navigation, URL restoration and browser history. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const [task,output]=process.argv.slice(2);
assert.ok(task && output,'Provide an existing completed task and evidence directory');
const launch=spawnSync('wsl.exe',['-d','Ubuntu','-u','root','--','/opt/agentscope/.venv/bin/python',
  '/opt/agentscope-history-v1/scripts/scope_browser_ticket.py'],{encoding:'utf8',windowsHide:true});
assert.equal(launch.status,0,'Could not create local browser session');
const modules=[['overview','总览'],['scope-demo','任务工作台'],['strategies','历史策略库'],
  ['task','任务与启动审核'],['agent-bridge','运行时 Agent 接入'],['governance','持久治理']];

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
  const report={mode:'real_service_read_only',task,desktop:[],narrow423:[],pageErrors:[],failedReads:[],passed:false};
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const page=await context.newPage();
    page.on('pageerror',e=>report.pageErrors.push(e.message));
    page.on('response',r=>{if(r.request().method()==='GET'&&r.status()>=400&&new URL(r.url()).pathname.startsWith('/api/'))
      report.failedReads.push({path:new URL(r.url()).pathname,status:r.status()});});
    const url=new URL(JSON.parse(launch.stdout.trim()).url);url.searchParams.set('task',task);
    await page.goto(url.toString());
    const sidebar=page.getByRole('navigation',{name:'工作区导航'});
    const assertPage=async(view,label)=>{
      await sidebar.getByRole('button',{name:label,exact:true}).waitFor({state:'visible'});
      await page.waitForFunction(name=>document.querySelector('#workspace-navigation button[aria-current="page"]')?.getAttribute('aria-label')===name,label);
      assert.equal(await sidebar.getByRole('button').count(),6);
      assert.equal(await page.locator('.sidebar').isVisible(),true);
      assert.equal(await page.locator('.topbar').count(),1);
      assert.equal(await page.locator('.scope-app-nav').count(),0);
      assert.equal(await page.locator('.topbar b').innerText(),label);
      assert.equal(new URL(page.url()).searchParams.get('view'),view);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Page overflow: '+view);
    };
    const visit=async(view,label)=>{await sidebar.getByRole('button',{name:label,exact:true}).click();await assertPage(view,label);};
    await page.getByRole('heading',{name:'任务工作台',exact:true}).waitFor();
    assert.equal(await page.getByLabel('管理员口令',{exact:true}).count(),0);
    assert.equal(await page.evaluate(()=>sessionStorage.getItem('agentscopeAdminToken')),null);
    assert.ok((await context.cookies()).find(c=>c.name==='agentscopeLocalSession')?.httpOnly);
    const originalBounds=await page.locator('.sidebar').boundingBox();
    for(const [view,label] of modules){
      await visit(view,label);
      const bounds=await page.locator('.sidebar').boundingBox();
      assert.equal(bounds.x,originalBounds.x);assert.equal(bounds.width,originalBounds.width);
      assert.equal(new URL(page.url()).searchParams.get('task'),task);
      await page.reload();await assertPage(view,label);
      report.desktop.push({view,refresh:'passed',sidebarWidth:bounds.width});
    }
    await visit('strategies','历史策略库');
    await page.getByRole('tab',{name:'策略记录与加载',exact:true}).click();
    assert.equal(new URL(page.url()).searchParams.get('section'),'records');
    await page.reload();await assertPage('strategies','历史策略库');
    assert.equal(await page.getByRole('tab',{name:'策略记录与加载',exact:true}).getAttribute('aria-selected'),'true');
    await page.getByRole('tab',{name:'生成记录与审计',exact:true}).click();
    await page.goBack();
    await page.waitForFunction(()=>document.querySelector('#history-tab-1')?.getAttribute('aria-selected')==='true');
    await page.goForward();
    await page.waitForFunction(()=>document.querySelector('#history-tab-2')?.getAttribute('aria-selected')==='true');
    report.historySectionRefreshAndBackForward='passed';
    await page.screenshot({path:path.join(output,'navigation-history-desktop.png'),fullPage:true});
    await visit('scope-demo','任务工作台');
    await page.goBack();await assertPage('strategies','历史策略库');
    await page.goForward();await assertPage('scope-demo','任务工作台');
    await page.getByRole('heading',{name:'任务工作台',exact:true}).waitFor();
    report.moduleBackForward='passed';
    await page.screenshot({path:path.join(output,'navigation-scope-desktop.png'),fullPage:true});

    const tasks=await page.evaluate(async()=>await(await fetch('/api/tasks')).json());
    const other=tasks.find(t=>t.dsh_profile==='web'&&t.id!==task);
    assert.ok(other,'An existing second registered managed workspace is required');
    const switchWorkspace=async()=>{
      await page.getByRole('button',{name:'切换工作区',exact:true}).click();
      await page.locator('.workspace-option').filter({hasText:other.workspace}).click();
      await page.locator('.workspace-strip code').filter({hasText:other.workspace}).waitFor();
    };
    await switchWorkspace();
    assert.equal(new URL(page.url()).searchParams.get('task'),other.id);
    await page.goBack();await page.locator('.workspace-strip').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('task'),task);
    await page.goForward();await page.locator('.workspace-strip').waitFor();
    assert.equal(new URL(page.url()).searchParams.get('task'),other.id);
    await page.reload();await page.locator('.workspace-strip').waitFor();
    report.taskRefreshAndBackForward='passed';
    await page.goto('http://127.0.0.1:18003/?view=runtime&task='+task);
    await assertPage('scope-demo','任务工作台');
    assert.equal(new URL(page.url()).searchParams.get('task'),task);
    report.retiredRuntimeRedirect='passed';

    await page.getByRole('button',{name:'收起侧栏',exact:true}).click();
    await visit('strategies','历史策略库');
    assert.equal(await page.getByRole('button',{name:'展开侧栏',exact:true}).getAttribute('aria-expanded'),'false');
    await page.reload();await assertPage('strategies','历史策略库');
    assert.equal(await page.getByRole('button',{name:'展开侧栏',exact:true}).getAttribute('aria-expanded'),'false');
    report.sidebarPreference='passed';
    await page.setViewportSize({width:423,height:900});
    for(const [view,label] of modules){
      await visit(view,label);
      assert.equal(await page.getByRole('button',{name:'展开侧栏',exact:true}).count(),1);
      report.narrow423.push({view,overflow:'none',sidebar:'visible'});
    }
    await visit('scope-demo','任务工作台');
    await page.getByRole('heading',{name:'任务工作台',exact:true}).waitFor();
    await page.screenshot({path:path.join(output,'navigation-scope-423.png'),fullPage:true});
    await visit('strategies','历史策略库');
    await page.screenshot({path:path.join(output,'navigation-history-423.png'),fullPage:true});
    await page.setViewportSize({width:1440,height:1000});
    await page.getByRole('button',{name:'展开侧栏',exact:true}).click();
    await assertPage('strategies','历史策略库');
    assert.equal((await page.locator('.sidebar').boundingBox()).width,originalBounds.width);
    assert.deepEqual(report.pageErrors,[]);assert.deepEqual(report.failedReads,[]);
    report.passed=true;
  } finally {
    fs.writeFileSync(path.join(output,'navigation-ui.json'),JSON.stringify(report,null,2));
    await browser.close();
  }
  console.log(JSON.stringify(report));
})().catch(e=>{console.error(e.message);process.exit(1)});
