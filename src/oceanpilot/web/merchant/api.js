async function requestJson(base,m,p,b){const o={method:m,headers:{'Content-Type':'application/json'}};
  if(b!==undefined)o.body=JSON.stringify(b);
  const run=()=>OceanRequest.json(base+p,o);
  return m==='GET'?run():OceanRequest.singleFlight(`${m}:${base+p}:${o.body||''}`,run);}
const api=(m,p,b)=>requestJson(BASE,m,p,b);
