export function replacementPolicyTarget(choices,targetId){
 if(!targetId||choices.some(row=>row.id===targetId))return '';
 return choices.length===1?choices[0].id:'';
}
