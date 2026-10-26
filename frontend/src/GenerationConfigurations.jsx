import React from 'react';
import PolicyRecordTable from './PolicyRecordTable.jsx';

export default function GenerationConfigurations({generation}){
 if(!generation.items?.length)return null;
 if(!generation.configuration_snapshots?.length)return <p>此轮配置快照暂不可用。</p>;
 return <section className="assistant-generated-results" aria-label="本轮生成的策略配置"><PolicyRecordTable rows={generation.configuration_snapshots} label="本轮策略记录" detail/><p className="assistant-snapshot-note">每项策略对应一条生成时记录；状态关联此版本的审批。</p></section>;
}
