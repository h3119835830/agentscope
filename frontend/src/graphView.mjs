export function layoutGraph(nodes,edges) {
  const ids=new Set(nodes.map(n=>n.key)),depth=new Map(nodes.map(n=>[n.key,0]));
  const valid=edges.filter(e=>ids.has(e.from)&&ids.has(e.to));
  for(let round=0;round<nodes.length;round++) {
    let changed=false;
    for(const edge of valid) {
      const next=Math.min(nodes.length,depth.get(edge.from)+1);
      if(next>depth.get(edge.to)){depth.set(edge.to,next);changed=true;}
    }
    if(!changed)break;
  }
  const levels=new Map();
  for(const n of nodes){const d=depth.get(n.key);if(!levels.has(d))levels.set(d,[]);levels.get(d).push(n);}
  const rowWidth=row=>row.length*224+(row.length-1)*32;
  const width=Math.max(680,...[...levels.values()].map(row=>rowWidth(row)+48));
  const positioned=nodes.map(n=>{
    const row=levels.get(depth.get(n.key));
    return {...n,x:(width-rowWidth(row))/2+row.indexOf(n)*256,y:28+depth.get(n.key)*124};
  });
  return {nodes:positioned,edges:valid,width,height:Math.max(220,...positioned.map(n=>n.y+110))};
}
