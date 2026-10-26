// Real page check against this task's SSH-forwarded ECS UI, no browser credentials.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const require=createRequire('C:/Users/happy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/package.json');
const {chromium}=require('playwright');
const session=process.env.AGENTSCOPE_ACCEPTANCE_SESSION||'session-49cc8f2b-5d6c-463f-8ce2-0e8eae5a10af';
const url='http://127.0.0.1:18030/?view=sessions&sessionInstance=instance-751ad8a6165f4357&sessionId='+encodeURIComponent(session)+'&sessionTab=audit';
const output='C:/Users/happy/Desktop/agentscope/acceptance/evidence/three-stage-20261025';
await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto(url);await page.getByRole('tab',{name:'评估与审计'}).waitFor();
 const close=page.getByRole('button',{name:'关闭公告'});if(await close.count())await close.click();
 await page.getByText('自动评估设置',{exact:false}).waitFor();
 await page.waitForFunction(()=>{const h=document.querySelector('.session-heading h1');return h&&h.textContent!=='会话详情';});
 await page.screenshot({path:output+'/audit-wide.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.getByText('自动评估设置',{exact:false}).click();
 await page.getByLabel('场景要求',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('对此 Agent 的新运行事件自动评估与审计',{exact:false}).isChecked(),true);
 await page.waitForFunction(()=>!!document.querySelector('.lifecycle-settings select')?.value);
 await page.screenshot({path:output+'/settings-wide.png',fullPage:true});
 await page.setViewportSize({width:850,height:1000});
 await page.screenshot({path:output+'/audit-compact.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 console.log(JSON.stringify({url,wide:'1440x1000',compact:'850x1000',horizontalOverflow:false,settingsScoped:true}));
}finally{await browser.close();}
