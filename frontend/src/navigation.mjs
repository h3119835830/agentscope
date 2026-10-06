export const pages = ['overview', 'scope-demo', 'strategies', 'task', 'agent-bridge', 'governance'];
export const historySections = ['generate', 'records', 'audit'];

export function readNavigation(href) {
  const url = new URL(href);
  const rawView = url.searchParams.get('view');
  const view = rawView==='runtime'?'scope-demo':rawView;
  const section = historySections.indexOf(url.searchParams.get('section'));
  const task = url.searchParams.get('task') || '';
  return {page: pages.includes(view) ? view : 'overview', historyModuleIndex: Math.max(0, section),
    task: /^[a-f0-9]{16}$/.test(task) ? task : ''};
}

export function navigationTarget(href, patch) {
  const url = new URL(href), next = {...readNavigation(href), ...patch};
  if(next.page==='runtime')next.page='scope-demo';
  if (!pages.includes(next.page)) throw new RangeError('Unknown module');
  if (!Number.isInteger(next.historyModuleIndex) || !historySections[next.historyModuleIndex]) throw new RangeError('Unknown history section');
  if (next.task && !/^[a-f0-9]{16}$/.test(next.task)) throw new RangeError('Invalid task');
  url.searchParams.set('view', next.page);
  if (next.page === 'strategies' || url.searchParams.has('section') || next.historyModuleIndex !== 0)
    url.searchParams.set('section', historySections[next.historyModuleIndex]);
  if (next.task) url.searchParams.set('task', next.task);
  else url.searchParams.delete('task');
  return url.pathname + url.search + url.hash;
}
