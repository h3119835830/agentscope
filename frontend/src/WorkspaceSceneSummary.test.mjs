import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { build } from 'esbuild';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const require = createRequire(import.meta.url);
const Module = require('node:module');
const base = dirname(fileURLToPath(import.meta.url));
const result = await build({
  entryPoints: [join(base, 'WorkspaceSceneSummary.jsx')], bundle: true,
  platform: 'node', format: 'cjs', external: ['react'], write: false,
});
const compiledPath = join(base, '.workspace-scene-summary-test.cjs');
const componentModule = new Module(compiledPath);
componentModule.paths = Module._nodeModulePaths(base);
componentModule._compile(result.outputFiles[0].text, compiledPath);
const WorkspaceSceneSummary = componentModule.exports.default;
const render = (props = {}) => renderToStaticMarkup(React.createElement(WorkspaceSceneSummary, props));

test('scene evidence remains escaped text and only explicit supplements are labelled as user input', () => {
  const html = render({
    name: '<img src=x onerror=alert(1)>', goal: '读取工作区',
    evidence: [
      { path: '<script>.md', quote: '<script>alert("scene")</script>', kind: 'asset' },
      { path: '', quote: '保留测试', kind: 'user_supplement' },
    ],
  });
  assert.doesNotMatch(html, /<script|<img|<details[^>]*\sopen(?:[\s=>])/);
  assert.match(html, /&lt;script&gt;alert/);
  assert.match(html, /来源类型<\/dt><dd>场景文件/);
  assert.match(html, /来源类型<\/dt><dd>用户补充/);
});

test('long goal starts in a native disclosure without truncating or changing its source text', () => {
  const goal = `  ${'Read the workspace and preserve existing tests. '.repeat(11)}\n保留原文。  `;
  const html = render({ name: '场景', goal });
  assert.match(html, /<details class="scene-goal-details">/);
  assert.match(html, /展开完整目标/);
  assert.doesNotMatch(html, /<details[^>]*\sopen(?:[\s=>])/);
  assert.ok(html.includes(`<p class="scene-goal-full">${goal}</p>`));
});

test('short goal stays directly readable while multiline goals can be expanded', () => {
  const html = render({ goal: '读取 README 并总结功能。' });
  assert.match(html, /读取 README 并总结功能。/);
  assert.doesNotMatch(html, /scene-goal-details|展开完整目标/);
  assert.match(render({ goal: '第一行\n第二行\n第三行\n第四行' }), /scene-goal-details/);
});

test('first two constraints are visible and remaining original constraints start folded', () => {
  const constraints = ['第一条', '第二条', 'Third requirement.', '第四条', '第五条'];
  const original = [...constraints];
  const html = render({ constraints });
  const [visible, folded] = html.split('<details class="scene-more-constraints">');
  assert.match(visible, /第一条/);
  assert.match(visible, /第二条/);
  assert.doesNotMatch(visible, /Third requirement\.|第四条|第五条/);
  assert.match(folded, /其余 3 条约束/);
  assert.match(folded, /Third requirement\./);
  assert.match(folded, /第五条/);
  assert.doesNotMatch(html, /<details[^>]*\sopen(?:[\s=>])/);
  assert.deepEqual(constraints, original);
});

test('empty recognition does not invent a goal or require a form field', () => {
  const html = render();
  assert.match(html, /尚未识别到本次目标/);
  assert.match(html, /尚未生成名称/);
  assert.doesNotMatch(html, /<(?:input|textarea|select)\b|\brequired\b|来源证据|scene-more-constraints/);
});
