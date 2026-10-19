export const attachmentTypes='.txt,.md,.json,.csv,.yaml,.yml,.log,.ini,.toml,.xml';
export async function readAttachments(files,existing=[]) {
 if(existing.length+files.length>10)throw Error('最多添加 10 个参考文件。');
 const result=[...existing];
 for(const file of files){
  if(!/\.(txt|md|json|csv|ya?ml|log|ini|toml|xml)$/i.test(file.name))throw Error('暂只支持 UTF-8 文本文件，PDF、Word 和图片暂不支持。');
  if(file.name.length>80||file.size>32000)throw Error('文件名最多 80 字符，每个文件最多 8000 字符。');
  if(result.some(f=>f.name===file.name))throw Error('已添加同名文件：'+file.name);
  let text;try{text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());}catch{throw Error(file.name+' 不是有效的 UTF-8 文本。');}
  if(!text.trim()||text.includes('\0')||text.length>8000)throw Error(file.name+' 需为非空文本，且不超过 8000 字符。');
  result.push({name:file.name,text});
 }
 return result;
}
export function conversationFor(history){
 return history.slice(-3).flatMap(g=>[
  {role:'user',content:g.text.slice(0,2000)},
  {role:'assistant',content:[...(g.questions||[]),...(g.gaps||[]),g.items?.length?'已起草 '+g.items.length+' 项配置，尚需审批。':''].filter(Boolean).join('\n').slice(0,3000)||'请继续补充需求。'}
 ]);
}
