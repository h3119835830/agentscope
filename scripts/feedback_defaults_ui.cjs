/* Real isolated API and built UI; no intercepted API or injected application state. */
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=process.argv[2];assert.ok(output);
const url='http://127.0.0.1:18005';
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const tokenRead=spawnSync('wsl',['-d','Ubuntu','-u','root','--exec','python3','-c',
    "from pathlib import Path;print(Path('/var/lib/agentscope-because-v1/admin-token').read_text(),end='')"],{encoding:'utf8'});
  assert.equal(tokenRead.status,0,'Cannot read isolated acceptance credential');
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  let page;
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1000},extraHTTPHeaders:{Authorization:'Bearer '+tokenRead.stdout}});
    page=await context.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const read=async()=>page.evaluate(async()=>{const r=await fetch('/api/security/system/policy-library');if(!r.ok)throw new Error('Policy library API '+r.status);return r.json();});
    await page.goto(url+'/?view=strategies&systemTab=policies');
    await page.getByRole('table',{name:'系统策略配置库'}).waitFor();
    await page.locator('.spl-record-name').first().waitFor();
    const before=await read();assert.equal(before.catalog.length,12);assert.equal(before.items.length,0);
    const checks=[];
    for(const preset of before.catalog){
      console.log('checking preset '+preset.id);
      await page.getByRole('button',{name:preset.name,exact:true}).click();
      const dialog=page.getByRole('dialog',{name:'配置系统策略'});
      const reason=dialog.getByLabel('反馈原因',{exact:true});assert.equal(await reason.inputValue(),preset.reason);
      await reason.fill(preset.reason+' 自定义补充。');
      await dialog.getByRole('button',{name:'取消',exact:true}).click();
      checks.push({id:preset.id,default_visible:true,editable:true});
    }
    const preset=before.catalog[0];
    await page.getByRole('button',{name:preset.name,exact:true}).click();
    let dialog=page.getByRole('dialog',{name:'配置系统策略'});
    const custom=preset.reason+' 请在公开报告中记录验证结果。';
    await dialog.getByLabel('反馈原因',{exact:true}).fill(custom);
    await dialog.getByRole('button',{name:'保存配置',exact:true}).click();
    await page.getByRole('status').filter({hasText:'已保存到配置库'}).waitFor();
    await page.reload();await page.getByRole('button',{name:preset.name,exact:true}).click();
    dialog=page.getByRole('dialog',{name:'配置系统策略'});
    assert.equal(await dialog.getByLabel('反馈原因',{exact:true}).inputValue(),custom);
    await dialog.getByRole('tab',{name:'原始 DSL',exact:true}).click();
    assert.ok((await dialog.innerText()).includes(custom));
    await dialog.getByRole('tab',{name:'配置策略',exact:true}).click();
    const saved=await read();assert.equal(saved.base_revision,before.base_revision);assert.equal(saved.base_hash,before.base_hash);
    assert.equal(saved.items.length,1);assert.equal(saved.items[0].applied,false);
    await page.screenshot({path:path.join(output,'custom-feedback-desktop.png'),fullPage:true});
    await dialog.getByRole('button',{name:'归档',exact:true}).click();
    await page.getByRole('status').filter({hasText:'配置已归档'}).waitFor();
    await page.getByRole('button',{name:preset.name,exact:true}).click();
    dialog=page.getByRole('dialog',{name:'配置系统策略'});
    assert.equal(await dialog.getByLabel('反馈原因',{exact:true}).inputValue(),preset.reason);
    await dialog.getByLabel('反馈原因',{exact:true}).scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,'default-feedback-desktop.png'),fullPage:true});
    await page.setViewportSize({width:423,height:900});
    await dialog.getByLabel('反馈原因',{exact:true}).scrollIntoViewIfNeeded();
    const size=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth}));assert.ok(size.width<=size.viewport);
    await page.screenshot({path:path.join(output,'default-feedback-423.png'),fullPage:true});
    const after=await read();assert.equal(after.items.length,0);assert.equal(after.base_hash,before.base_hash);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'ui-acceptance.json'),JSON.stringify({passed:true,url,checks,custom_round_trip:true,
      because_preview:true,no_application:true,base_revision:after.base_revision,base_hash:after.base_hash,
      acceptance_draft_archived:true,narrow423:true,page_errors:errors},null,2));
    console.log(JSON.stringify({passed:true,presets:checks.length,custom_round_trip:true,no_application:true,narrow423:true}));
  }catch(e){
    if(page){await page.screenshot({path:path.join(output,'ui-failure.png'),fullPage:true});
      fs.writeFileSync(path.join(output,'ui-failure.txt'),await page.locator('dialog').allTextContents().then(x=>x.join('\n')));}
    throw e;
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
