import React from 'react';

const textValue = (value) => typeof value === 'string' ? value : '';
const hasText = (value) => textValue(value).trim().length > 0;

export default function WorkspaceSceneSummary({ name, goal, summary, constraints = [], evidence = [] }) {
  const sceneName = textValue(name);
  const sceneGoal = textValue(goal);
  const sceneSummary = textValue(summary);
  const sceneConstraints = Array.isArray(constraints) ? constraints.map(textValue).filter(hasText) : [];
  const foldGoal = hasText(sceneGoal) && (sceneGoal.length > 180 || sceneGoal.split(/\r?\n/).length > 3);
  const sceneEvidence = Array.isArray(evidence)
    ? evidence.filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    : [];

  return (
    <section className="scene-result" aria-label="识别结果">
      <h3>识别结果</h3>
      <dl className="scene-fields">
        <dt>名称</dt>
        <dd>{hasText(sceneName) ? <>{sceneName} <span>（自动生成）</span></> : '尚未生成名称'}</dd>
        <dt>任务目标</dt>
        <dd>{foldGoal ? (
          <details className="scene-goal-details">
            <summary>
              <span className="scene-goal-preview">{sceneGoal}</span>
              <span className="scene-disclosure-toggle scene-when-closed">展开完整目标</span>
              <span className="scene-disclosure-toggle scene-when-open">收起完整目标</span>
            </summary>
            <p className="scene-goal-full">{sceneGoal}</p>
          </details>
        ) : hasText(sceneGoal) ? sceneGoal : '尚未识别到本次目标'}</dd>
        {hasText(sceneSummary) && <><dt>项目说明</dt><dd>{sceneSummary}</dd></>}
        {sceneConstraints.length > 0 && <>
          <dt>场景约束</dt>
          <dd>
            <ul className="scene-constraints">
              {sceneConstraints.slice(0, 2).map((constraint, index) => <li key={index}>{constraint}</li>)}
            </ul>
            {sceneConstraints.length > 2 && (
              <details className="scene-more-constraints">
                <summary>其余 {sceneConstraints.length - 2} 条约束</summary>
                <ul className="scene-constraints">
                  {sceneConstraints.slice(2).map((constraint, index) => <li key={index}>{constraint}</li>)}
                </ul>
              </details>
            )}
          </dd>
        </>}
      </dl>
      {sceneEvidence.length > 0 && (
        <details className="scene-sources">
          <summary>来源证据（{sceneEvidence.length} 条）</summary>
          <ol className="scene-constraints">
            {sceneEvidence.map((item, index) => (
              <li key={index}>
                <dl className="scene-fields">
                  <dt>来源类型</dt>
                  <dd>{item.kind === 'user_supplement' ? '用户补充' : '场景文件'}</dd>
                  <dt>来源路径</dt>
                  <dd>{hasText(item.path) ? item.path : '未记录来源路径'}</dd>
                  <dt>引用内容</dt>
                  <dd>{hasText(item.quote) ? item.quote : '未记录摘录'}</dd>
                </dl>
              </li>
            ))}
          </ol>
        </details>
      )}
    </section>
  );
}
