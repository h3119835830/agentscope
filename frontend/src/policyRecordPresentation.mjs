export const operationLabel=value=>({open:'打开文件',read:'读取',write:'写入',unlink:'删除',exec:'执行程序',connect:'连接'})[value]||value;
export const effectLabel=value=>({block:'阻止并反馈',notify:'记录并提醒',kill:'终止违规进程'})[value]||value;
