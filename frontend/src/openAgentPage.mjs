// Resolve the current native entry on every click; never cache a launch URL.
export async function openAgentPage({id,start=false,prepareStart,post,browser=window}){
 const target=browser.open('about:blank','_blank');
 if(!target)throw Error('浏览器阻止新标签页，请允许弹出窗口后重试');
 target.opener=null;
 try{
  const path='/api/agent-instances/'+encodeURIComponent(id);
  if(start&&(!prepareStart||await prepareStart()))await post(path+'/start');
  let result;
  try{result=await post(path+'/open');}
  catch(error){throw Object.assign(new Error(error.message),{entryUnavailable:true});}
  let url;
  try{url=new URL(result.url);}catch{throw Error('原生页面地址未通过本机核验');}
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password)throw Error('原生页面地址未通过本机核验');
  // Keep the native launch on the console's loopback hostname, preserving auth and port.
  if(browser.location?.hostname==='localhost')url.hostname='localhost';
  if(target.closed)throw Error('新标签页已关闭，请重新点击打开');
  target.location.replace(url.href);
 }catch(error){target.close();throw error;}
}
