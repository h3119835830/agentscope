import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {archiveLensEvents,scheduleArchiveScroll} from './archiveRecords.mjs';
test('historical event lenses retain separate evidence classes without inventing server categories',()=>{
 const events=['file_snapshot','task_context','startup_job','startup_finished','policy_version','policy_active','operation_verified'].map(kind=>({id:kind,kind}));
 assert.deepEqual(archiveLensEvents(events,'files').map(e=>e.kind),['file_snapshot','task_context']);
 assert.deepEqual(archiveLensEvents(events,'generation').map(e=>e.kind),['startup_job','startup_finished']);
 assert.deepEqual(archiveLensEvents(events,'versions').map(e=>e.kind),['policy_version','policy_active']);
});
test('history route preserves selected task but cannot mount live workbench or global refresh',()=>{
 const main=readFileSync(new URL('./main.jsx',import.meta.url),'utf8');
 assert.match(main,/page!=='history'&&<div hidden=\{page!=='connections'\}><AgentWorkspaces/);
 assert.match(main,/page==='workbench'&&<ConsoleWorkbench/);
 assert.doesNotMatch(main,/<TaskHub|<ManagedWorkbench|<Overview /);
 assert.match(main,/const refresh = useCallback\(async \(\) => \{\s*if\(page==='history'\)return/);
 assert.match(main,/useEffect\(\(\) => \{ if\(page==='history'\)return; refresh\(\)/);
 assert.match(main,/<ProductOverview /);
 assert.doesNotMatch(main,/page==='history'.*navigate\(\{task:''/);
 assert.doesNotMatch(main,/archiveTask:selected&&isTaskEnded/);
 assert.doesNotMatch(main,/>任务回放<\/button>|历史策略与审计/);
 assert.match(main,/label="任务历史"/);
 assert.match(main,/<TaskArchive api=\{api\}/);
});

test('opening replay resets old list scroll and cancelled frames cannot overwrite it; returning restores list position',()=>{
 let y=940,next=0,focused=0;const queue=new Map(),requestFrame=fn=>{queue.set(++next,fn);return next;},cancelFrame=id=>queue.delete(id),viewport={scrollTo:({top})=>{y=top;}},flush=()=>{for(const [id,fn] of [...queue]){queue.delete(id);fn();}};
 const listCleanup=scheduleArchiveScroll({task:'',position:940,window:viewport,requestFrame,cancelFrame});listCleanup();
 const replayCleanup=scheduleArchiveScroll({task:'task-10',position:940,heading:{focus:options=>{assert.equal(options.preventScroll,true);focused++;}},window:viewport,requestFrame,cancelFrame});
 assert.equal(y,0);flush();flush();assert.equal(y,0);assert.ok(focused>0);replayCleanup();
 const returnCleanup=scheduleArchiveScroll({task:'',position:940,window:viewport,requestFrame,cancelFrame});assert.equal(y,940);flush();flush();assert.equal(y,940);returnCleanup();assert.equal(queue.size,0);
});
