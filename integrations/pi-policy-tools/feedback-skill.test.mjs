import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {DefaultResourceLoader} from './node_modules/@earendil-works/pi-coding-agent/dist/core/resource-loader.js';
import {AgentSession} from './node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.js';

test('native Pi explicitly loads and expands feedback Skill while ambient discovery stays disabled',async()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'pi-feedback-skill-'));
  try {
    const ambient=path.join(root,'.pi/skills/ambient');fs.mkdirSync(ambient,{recursive:true});
    fs.writeFileSync(path.join(ambient,'SKILL.md'),'---\nname: ambient\ndescription: Untrusted project skill\n---\nUNTRUSTED INSTRUCTIONS');
    const skill=fileURLToPath(new URL('./skills/policy-feedback/SKILL.md',import.meta.url));
    const loader=new DefaultResourceLoader({cwd:root,agentDir:path.join(root,'agent'),noSkills:true,
      noExtensions:true,noContextFiles:true,noPromptTemplates:true,noThemes:true,additionalSkillPaths:[skill]});
    await loader.reload();
    assert.deepEqual(loader.getSkills().skills.map(s=>s.name),['policy-feedback']);
    assert.deepEqual(loader.getSkills().diagnostics,[]);
    const content=AgentSession.prototype._expandSkillCommand.call({resourceLoader:loader},'/skill:policy-feedback Generate the bound policy.');
    const body=fs.readFileSync(skill,'utf8').split('\n---\n')[1].trim();
    assert.ok(content.startsWith('<skill name="policy-feedback"'));
    assert.ok(content.includes(body));assert.ok(content.endsWith('Generate the bound policy.'));
    assert.ok(!content.includes('UNTRUSTED INSTRUCTIONS'));
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
