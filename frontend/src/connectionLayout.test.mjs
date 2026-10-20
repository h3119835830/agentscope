import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import postcss from 'postcss';

const css = readFileSync(new URL('./agentInstances.css', import.meta.url), 'utf8');
const marker = '/* Existing connection settings use the same compact launch layout as Add. */';
const root = postcss.parse(css.slice(css.indexOf(marker)));
const prefix = '.instance-drawer #instance-pane-connection ';
const declaration = (selector, prop, media = false) => {
  let value;
  root.walkRules(selector, rule => {
    if ((rule.parent.type === 'atrule') === media)
      rule.walkDecls(prop, decl => { value = decl.value; });
  });
  return value;
};

test('compact settings never change Add or the resources/workspaces/events tabs', () => {
  assert.ok(css.includes(marker));
  let count = 0;
  root.walkRules(rule => {
    for (const selector of rule.selectors) {
      assert.ok(selector.startsWith(prefix), selector);
      count++;
    }
  });
  assert.equal(count, 10);
});

test('launch mode and web entry share a row; narrow screens use one column', () => {
  assert.equal(declaration(prefix + '.agent-launch-fields', 'grid-template-columns'), 'repeat(2,minmax(0,1fr))');
  assert.equal(declaration(prefix + '.agent-launch-fields', 'grid-template-columns', true), 'minmax(0,1fr)');
  assert.equal(declaration(prefix + '.instance-form', 'gap'), '14px 16px');
  assert.equal(declaration(prefix + '.instance-form label', 'gap'), '6px');
  const responsive = root.nodes.find(node => node.type === 'atrule');
  assert.equal(responsive.params, '(max-width:650px)');
  const spans = [];
  root.walkDecls('grid-column', decl => spans.push(...decl.parent.selectors));
  assert.deepEqual(spans, [prefix + '.agent-launch-fields>label:nth-of-type(1)',
    prefix + '.agent-launch-fields>label:nth-of-type(2)', prefix + '.agent-launch-fields>p']);
});
