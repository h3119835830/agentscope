from pathlib import Path

def operation_feedback(event_id, raw, task):
    target=str(raw.get('target',''))
    roots=[task['workspace'],task['output_dir'],str(Path(task['workspace']).parent/'tmp')]
    visible=any(target==root or target.startswith(root+'/') for root in roots) and '/.actplane' not in target
    return {'id':event_id,'operation':str(raw.get('op','operation')),'target':target if visible else '<outside task execution environment>','result':'denied','reason':'The execution environment denied this operation.','alternative':'Continue using task project materials and another task operation; ask the user if a required action remains unavailable.'}
