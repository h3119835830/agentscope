// Capture real pages only. No request interception, mocked responses or DOM edits.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('node:fs/promises');
async function main(){
 const [task,out,mode='native',selectText,action]=process.argv.slice(2);
 if(!task||!out)throw Error('task and screenshot path are required');
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1480,height:1080},deviceScaleFactor:1});
  await page.goto(mode==='native'?`http://127.0.0.1:18005/api/managed/tasks/${encodeURIComponent(task)}/open`:mode,{waitUntil:'networkidle'});
  await page.waitForTimeout(1800);
  if(action==='inspect-navigation'){console.log(JSON.stringify({navigation:await page.locator('body').innerText()}));return;}
  if(selectText){await page.getByText(selectText,{exact:true}).first().click();await page.waitForTimeout(1000);}
  if(action==='answer-read-only'){await page.getByText('先不删，只给我一份分类清单',{exact:true}).click();await page.getByRole('button',{name:'提交',exact:true}).click();await page.waitForTimeout(1000);}
  if(action==='skip-question'){await page.getByRole('button',{name:'跳过',exact:true}).click();return;}
  if(action==='show-dsl'){await page.locator('button.policy-record').filter({hasText:'memory-note.txt'}).first().click();await page.getByRole('tab',{name:'DSL',exact:true}).click();}
  if(action==='memory-hook'){await page.getByRole('row').filter({hasText:'跨会话持久记忆加载'}).getByRole('button',{name:'查看详情',exact:true}).click();}
  if(action==='audit'){await page.getByRole('tab',{name:'执行审计',exact:true}).click();await page.waitForTimeout(1000);}
  if(mode==='native'){
   // Capture the visible public assistant output only, excluding private reasoning.
   const block=page.locator('div.hWmORq_body div[class^="_markdown_"]').filter({hasText:'青鹭-跨会话-7426'}).last();
   await block.screenshot({path:out});
  }else{if(action==='show-dsl')await page.getByRole('dialog').screenshot({path:out});else if(action==='memory-hook')await page.locator('section.runtime-hook-record').screenshot({path:out});else await page.screenshot({path:out,fullPage:true});await fs.writeFile(out+'.txt',await page.locator('body').innerText());}
  console.log(JSON.stringify({screenshot:out,title:await page.title(),...(mode==='native'?{}:{text:(await page.locator('body').innerText()).slice(-10000)})}));
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e.message);process.exitCode=1});
