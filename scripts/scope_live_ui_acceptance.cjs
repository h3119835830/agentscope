/* Real service + Pi + DSH + kernel acceptance. No API interception or state injection. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {spawn,spawnSync}=require('node:child_process');
const readline=require('node:readline');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=process.argv[2];
assert.ok(output,'Provide an evidence output directory');
const sequence=['S0','S1_pending','S1','S2_pending','S2','S3_pending','S3_rejected','S3_retry_pending','S3','S4'];
const revision={S0:0,S1_pending:0,S1:1,S2_pending:1,S2:2,S3_pending:2,S3_rejected:2,S3_retry_pending:2,S3:3,S4:3};
const titles={task_grant:'开放任务目录',restrict:'收紧修改范围',expand:'开放报告目录'};
const ticket=spawnSync('wsl.exe',['-d','Ubuntu','-u','root','--','/opt/agentscope/.venv/bin/python',
  '/opt/agentscope-history-v1/scripts/scope_browser_ticket.py'],{encoding:'utf8',windowsHide:true});
assert.equal(ticket.status,0,'Could not create trusted local browser session');
const entrance=JSON.parse(ticket.stdout.trim()).url; // One-use ticket stays in memory.

(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||'chrome'});
  const report={mode:'real_service_and_execution',taskSource:'custom_standard_library_fixture',
    approvalSource:'user_authorized_bounded_acceptance_driver',apiReplay:false,checkpoints:[],pageErrors:[],passed:false};
  let driver,task,failure,stderr='',driverResult;
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000}});
    const page=await context.newPage();
    page.on('pageerror',e=>report.pageErrors.push(e.message));
    const getScope=()=>page.evaluate(async id=>{
      const response=await fetch('/api/tasks/'+id+'/scope-manager');
      if(!response.ok)throw new Error('Scope API '+response.status);
      return response.json();
    },task);
    const permissions=async scope=>{
      assert.equal(await page.locator('.scope-permissions tbody tr').count(),6);
      for(const resource of ['backend','frontend','tests','config','output']){
        const row=page.locator('.scope-pane .scope-permissions tbody tr').filter({has:page.locator('td').getByText(resource,{exact:true})});
        const allowed=resource==='output'?scope.allow_output:(scope.allowed_write_dirs||[]).includes(resource);
        assert.equal(await row.getByText(allowed?'可读写':['tests','config'].includes(resource)?'只读 · 保护':'只读',{exact:true}).count(),1,resource);
      }
    };
    const noOverflow=async()=>{
      const size=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth}));
      assert.ok(size.width<=size.viewport,JSON.stringify(size));
    };
    const verifyCheckpoint=async event=>{
      assert.equal(event.checkpoint,sequence[report.checkpoints.length],'Unexpected stage ordering');
      if(!task){
        task=event.task;report.task=task;
        const url=new URL(entrance);url.searchParams.set('task',task);
        await page.goto(url.toString());
      }else{
        assert.equal(event.task,task);
        await page.reload();
      }
      const stage=event.checkpoint;
      await page.getByRole('heading',{name:stage==='S4'?'结束前的权限':'当前有效权限',exact:true}).waitFor();
      const state=await getScope();
      assert.equal(state.current.revision,revision[stage]);
      assert.equal(state.current.verification.passed,true);
      assert.ok(state.current.verification.root_owned_events);
      assert.ok(state.current.verification.probe.checks.every(c=>c.passed),'Actual kernel probe failed');
      assert.equal(await page.getByLabel('选择 Demo 任务').inputValue(),task);
      assert.equal(await page.getByLabel('管理员口令',{exact:true}).count(),0);
      assert.equal(await page.evaluate(()=>sessionStorage.getItem('agentscopeAdminToken')),null);
      assert.ok((await context.cookies()).find(c=>c.name==='agentscopeLocalSession')?.httpOnly);
      assert.equal(new URL(page.url()).hash,'');
      assert.equal(await page.locator('.sidebar').isVisible(),false);
      await permissions(state.current.payload);
      await page.getByRole('button',{name:'DSH 连接详情',exact:true}).click();
      const connection=page.getByRole('dialog');await connection.waitFor({state:'visible'});
      const copy=await connection.innerText();
      if(state.session.phase==='ended')assert.ok(copy.includes('任务已结束')&&!copy.includes('PID '));
      else if(state.session.phase==='cold')assert.ok(copy.includes('DSH 尚未启动')&&!copy.includes('PID '));
      else if(state.effective&&state.execution.executor?.state==='running'){
        assert.ok(copy.includes('PID '+state.execution.executor.pid));assert.ok(copy.includes('DSH 进程运行中'));
      }else assert.ok(!copy.includes('DSH 进程运行中'));
      assert.ok(copy.includes('空闲期间没有独立心跳'));
      await page.screenshot({path:path.join(output,stage+'-connection.png'),fullPage:true});
      await page.keyboard.press('Escape');
      if(stage==='S4'){
        assert.equal(state.effective,false);
        assert.equal(state.session.phase,'ended');
        assert.equal(await page.locator('.scope-stages button.done').count(),5);
        assert.equal(await page.getByRole('button',{name:'结束并撤销',exact:true}).count(),0);
      }else assert.equal(state.effective,true);
      if(stage==='S2_pending'){
        assert.equal(state.session.gate,'waiting_constraint');
        assert.equal(await page.getByText('等待收紧生效',{exact:true}).first().isVisible(),true);
        assert.ok(state.current.payload.allowed_write_dirs.includes('frontend'),'Pending restriction changed active scope');
      }
      if(stage.startsWith('S3')&&stage!=='S3'){
        assert.equal(state.current.payload.allow_output,false,'Unapproved/rejected expansion changed active scope');
        assert.deepEqual(state.current.payload.allowed_write_dirs,['backend']);
      }
      if(event.delta){
        const delta=state.deltas.find(d=>d.id===event.delta);assert.ok(delta);
        const processed=stage==='S3_rejected';
        assert.equal(delta.review_status,processed?'rejected':'pending');
        await page.getByRole('tab',{name:/变更审核/}).click();
        if(processed)await page.getByRole('button',{name:'已处理',exact:true}).click();
        const row=page.locator('[data-delta-id="'+event.delta+'"]');
        await row.getByRole('button',{name:titles[delta.kind]+'，查看申请',exact:true}).click();
        const drawer=page.getByRole('dialog');await drawer.waitFor({state:'visible'});
        if(processed)assert.equal(await drawer.getByRole('button',{name:'批准并应用',exact:true}).count(),0);
        else{
          assert.equal(delta.base_snapshot_id,state.current.id);
          assert.equal(delta.message_revision,state.session.message_revision);
          assert.equal(delta.process_epoch,state.session.process_epoch);
          assert.equal(await drawer.getByRole('button',{name:'批准并应用',exact:true}).isEnabled(),true);
          assert.equal(await drawer.locator('.scope-diff-list>div').count(),stage==='S1_pending'?2:1);
        }
        assert.equal(await drawer.locator('.scope-pi-explanation p').isVisible(),false);
        assert.equal(await drawer.locator('pre').isVisible(),false);
      }
      await page.screenshot({path:path.join(output,stage+'.png'),fullPage:true});
      await page.setViewportSize({width:423,height:900});await noOverflow();
      await page.screenshot({path:path.join(output,stage+'-423.png'),fullPage:true});
      if(event.delta){
        await page.keyboard.press('Escape');
        assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),titles[state.deltas.find(d=>d.id===event.delta).kind]+'，查看申请');
      }
      await page.getByRole('tab',{name:'执行记录',exact:true}).click();
      const lines=await page.locator('.scope-records li').allTextContents();
      assert.ok(lines.length<=8&&lines.every(s=>s.length<90&&!s.includes('proposal_hash')&&!s.includes('/s/')));
      await noOverflow();
      await page.screenshot({path:path.join(output,stage+'-records-423.png'),fullPage:true});
      await page.setViewportSize({width:1440,height:1000});
      report.checkpoints.push({stage,revision:state.current.revision,snapshot:state.current.id,domain:state.current.binding.domain_id,
        processEpoch:state.session.process_epoch,gate:state.session.gate,effective:state.effective,
        delta:event.delta,probeChecks:state.current.verification.probe.checks.length,
        actualKernelEvidence:true,connectionEvidence:'passed',desktop:'passed',narrow423:'passed',compactRecords:'passed'});
      fs.writeFileSync(path.join(output,'scope-live-ui.json'),JSON.stringify(report,null,2));
      console.log(JSON.stringify({stage:'browser_checked',checkpoint:stage,task,revision:state.current.revision}));
    };
    driver=spawn('wsl.exe',['-d','Ubuntu','-u','root','--','/opt/agentscope/.venv/bin/python',
      '/opt/agentscope-history-v1/scripts/scope_full_acceptance.py','--live-ui'],{windowsHide:true,stdio:['pipe','pipe','pipe']});
    const exited=new Promise((resolve,reject)=>{
      driver.once('error',reject);driver.once('close',(code,signal)=>resolve({code,signal}));
    });
    driver.stderr.on('data',chunk=>{stderr=(stderr+chunk.toString()).slice(-6000);});
    for await(const line of readline.createInterface({input:driver.stdout,crlfDelay:Infinity})){
      let event;try{event=JSON.parse(line);}catch{continue;}
      if(event.stage==='ui_checkpoint'){
        if(!failure)try{await verifyCheckpoint(event);}catch(error){failure=error;}
        driver.stdin.write(JSON.stringify({checkpoint:event.checkpoint,task:event.task,status:failure?'failed':'passed'})+'\n');
      }else if(event.passed===true)driverResult=event;
      else if(event.stage)console.log(JSON.stringify(event));
    }
    const exit=await exited;
    report.driverExit=exit.code;
    assert.equal(exit.code,0,failure?.message||'Real execution driver failed');
    if(failure)throw failure;
    assert.ok(driverResult?.passed);
    assert.equal(report.checkpoints.length,sequence.length);
    const v1=report.checkpoints.find(s=>s.stage==='S1'),v2=report.checkpoints.find(s=>s.stage==='S2'),v3=report.checkpoints.find(s=>s.stage==='S3');
    assert.equal(v1.domain,v2.domain);
    assert.notEqual(v2.domain,v3.domain);
    assert.notEqual(v2.processEpoch,v3.processEpoch);
    assert.equal(report.pageErrors.length,0,report.pageErrors.join(';'));
    report.execution=driverResult;report.passed=true;
    fs.writeFileSync(path.join(output,'scope-live-ui.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify({task,passed:true,realUiCheckpoints:report.checkpoints.length,apiReplay:false,evidence:path.join(output,'scope-live-ui.json')}));
  }catch(error){
    report.error=error.message;report.driverDiagnostic=stderr;
    fs.writeFileSync(path.join(output,'scope-live-ui.json'),JSON.stringify(report,null,2));
    throw error;
  }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
