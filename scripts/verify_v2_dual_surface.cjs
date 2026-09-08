const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.V2_QA_BASE || 'http://127.0.0.1:8013';
fs.mkdirSync('work/dual-surface-qa', { recursive: true });
const headers = { 'Content-Type':'application/json','X-Demo-Role':'OPERATOR','X-Demo-Actor':'synthetic-operator','X-Demo-Merchant':'synthetic-merchant-001' };
const report = { checks:[], synchronization_ms:[], errors:[] };
async function json(path, options={}) { const r=await fetch(base+'/api/v2'+path,{...options,headers:{...headers,...options.headers}}); const b=await r.json(); assert.ok(r.ok,JSON.stringify(b)); return b; }
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_EXECUTABLE || (process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : undefined),headless:true});
 try {
  const b=(await json('/demo',{method:'POST',body:JSON.stringify({scenario:'B'})})).case;
  report.case_id=b.id;
  const other=(await json('/demo',{method:'POST',body:JSON.stringify({scenario:'A'})})).case;
  const cm=await browser.newContext({viewport:{width:1440,height:1000}}), co=await browser.newContext({viewport:{width:1440,height:1000}});
  const m=await cm.newPage(),o=await co.newPage();
  for(const p of [m,o])p.on('pageerror',e=>report.errors.push(e.message));
  const loaded=async(p,id)=>p.waitForFunction(id=>window.OceanV2?.state.current?.id===id&&!!OceanV2.state.activity,id,{timeout:15000});
  const rev=async p=>p.evaluate(()=>OceanV2.state.current.revision);
  const checkSync=async(p,v,from)=>{await p.waitForFunction(v=>OceanV2.state.current?.revision>=v,v,{timeout:7000});report.synchronization_ms.push(Date.now()-from);};
  const tab=async(p,t)=>p.locator('#caseDetail .detail-tabs [data-tab="'+t+'"]').click();
  const role=async(r)=>{await o.locator('#roleSelect').selectOption(r);await o.waitForFunction(r=>OceanV2.state.role===r&&!OceanV2.state.loading&&!!OceanV2.state.current,r);};
  const act=async(p,a,values={})=>{
   await p.locator('#caseDetail [data-action="'+a+'"]').first().click();
   await p.locator('#actionDialog').waitFor({state:'visible'});
   for(const [k,v] of Object.entries(values)){
    const f=p.locator('#dialogFields [name="'+k+'"]');
    const tag=await f.evaluate(e=>e.tagName.toLowerCase());
    if(typeof v==='boolean')await f.setChecked(v);else if(tag==='select')await f.selectOption(String(v));else await f.fill(String(v));
   }
   await p.locator('#confirmCheckbox').check();
   const old=await rev(p);
   await p.locator('#submitDialog').click();
   await p.locator('#actionDialog').waitFor({state:'hidden',timeout:15000});
   await p.waitForFunction(v=>OceanV2.state.current?.revision>v&&!OceanV2.state.loading,old,{timeout:15000});
   return await rev(p);
  };
  await Promise.all([m.goto(base+'/v2/merchant'),o.goto(base+'/v2/operations')]);
  for(const p of [m,o])await p.waitForFunction(()=>window.OceanV2&&!OceanV2.state.loading&&OceanV2.state.cases.length>=2);
  assert.equal(await m.locator('#agentPanel').isVisible(),false);assert.equal(await o.locator('#caseDetail').isVisible(),false);
  assert.ok(await m.locator('.merchant-case-link').count());assert.ok(await o.locator('.operations-case-table').count());
  report.checks.push('distinct merchant / OP list pages without auto-selected AI');
  const fresh=(await json('/demo',{method:'POST',body:JSON.stringify({scenario:'A'})})).case;
  await Promise.all([m,o].map(p=>p.waitForFunction(id=>OceanV2.state.cases.some(c=>c.id===id),fresh.id)));
  report.checks.push('new case automatically appears in both open list pages');
  await m.locator('.merchant-case-link[href$="/'+b.id+'"]').click();await o.locator('.table-case-link[href$="/'+b.id+'"]').click();
  await Promise.all([loaded(m,b.id),loaded(o,b.id)]);
  assert.ok(m.url().includes('/cases/'));assert.equal(await m.locator('#caseDetail [data-tab="review"]').count(),0);
  report.checks.push('dedicated case URLs / merchant excludes operational actions');
  await m.locator('#agentMessage').fill('未发送的本案问题，将在远端更新时保留');
  await tab(m,'collaboration');await m.locator('#caseDetail [data-action="COMMENT"]').first().click();
  await m.locator('#dialogFields [name="message"]').fill('未提交的业务表单内容');
  await m.locator('#confirmCheckbox').check();
  await tab(o,'collaboration');let start=Date.now();let v=await act(o,'COMMENT',{message:'请补充地址匹配与沟通记录，跨端同步检查'});await checkSync(m,v,start);
  assert.equal(await m.locator('#dialogFields [name="message"]').inputValue(),'未提交的业务表单内容');
  assert.equal(await m.locator('#submitDialog').isDisabled(),true);assert.equal(await m.locator('#confirmCheckbox').isChecked(),false);
  assert.equal(await m.locator('#agentMessage').inputValue(),'未发送的本案问题，将在远端更新时保留');
  await m.locator('#cancelDialog').click();report.checks.push('OP → merchant auto sync preserves draft and invalidates old confirmation');
  await tab(m,'evidence');
  for(let i=0;await m.locator('.evidence-row [data-action="REGISTER_EVIDENCE"]').count();i++){
   assert.ok(i<10,"evidence checklist did not converge");
   await m.locator('.evidence-row [data-action="REGISTER_EVIDENCE"]').first().click();
   await m.locator('#dialogFields [name="reference"]').fill('synthetic://dual-surface-qa/evidence-'+i);
   await m.locator('#dialogFields [name="notes"]').fill('合成证据引用，跨端完整流程验证');
   await m.locator('#confirmCheckbox').check();let old=await rev(m);start=Date.now();
   await m.locator('#submitDialog').click();await m.locator('#actionDialog').waitFor({state:'hidden'});
   await m.waitForFunction(v=>OceanV2.state.current.revision>v&&!OceanV2.state.loading,old);
   await checkSync(o,await rev(m),start);
  }
  start=Date.now();v=await act(m,'SUBMIT_EVIDENCE');await checkSync(o,v,start);
  assert.equal(await o.evaluate(()=>OceanV2.state.current.work_status),'OP_REVIEW');
  report.checks.push('merchant evidence registration / send to OP synchronizes without refresh');
  await role('RISK_OFFICER');await tab(o,'review');start=Date.now();v=await act(o,'REVIEW',{decision:'REVISION',reason:'请确认沟通记录明确包含配送地址，本轮退回补证。'});await checkSync(m,v,start);
  await tab(m,'tasks');assert.match(await m.locator('#caseDetail').innerText(),/请确认沟通记录明确包含配送地址/);
  report.checks.push('risk review feedback appears in merchant tasks automatically');
  await tab(m,'evidence');v=await act(m,'SUBMIT_EVIDENCE');await checkSync(o,v,Date.now());
  await act(o,'REVIEW',{decision:'PASS',reason:'合成演示已人工检查全部证据内容，确认通过。'});
  await role('OPERATOR');await act(o,'BUILD_PACKAGE');
  await role('SUPERVISOR');await act(o,'APPROVE_PACKAGE',{reason:'独立终审已核对当前证据包与来源。',pii_checked:true});
  await role('OPERATOR');start=Date.now();v=await act(o,'SUBMIT');await checkSync(m,v,start);
  assert.equal(await m.evaluate(()=>OceanV2.state.current.work_status),'WAITING_UPSTREAM');
  report.checks.push('risk PASS → package → independent supervisor freeze → mock upstream receipt');
  await tab(o,'outcome');await act(o,'RECORD_OUTCOME',{outcome:'WON',final:true,source:'MOCK_UPSTREAM',reason:'合成上游确认终局胜诉'});
  await act(o,'RECORD_FINANCIAL',{kind:'CREDIT',amount_minor:12800,currency:'USD',source:'MOCK_UPSTREAM',reference:'synthetic://dual-surface-qa/credit'});
  await role('SUPERVISOR');await act(o,'RECONCILE',{status:'RECONCILED',expected_net_minor:12800,reason:'独立核对合成账单与资金流水一致',reference:'synthetic://dual-surface-qa/reconcile'});
  await role('OPERATOR');await act(o,'NOTIFY_MERCHANT',{message:'合成案件已终局胜诉，资金核对完成。',channel:'PORTAL'});
  await role('SUPERVISOR');start=Date.now();v=await act(o,'CLOSE');await checkSync(m,v,start);
  assert.equal(await m.evaluate(()=>OceanV2.state.current.work_status),'CLOSED');report.checks.push('upstream result → independent reconciliation → merchant notice → closure');
  // Separate case and audience conversations remain distinct.
  await m.locator('#agentMessage').fill('商户独有标记：客户需要了解已结案的处理结果');
  await m.locator('#agentMessageForm button[type="submit"]').click();await m.waitForFunction(()=>!OceanV2.state.agentBusy&&OceanV2.state.activity.conversations.some(c=>c.message?.includes('商户独有标记')));
  await role('OPERATOR');await o.locator('#agentMessage').fill('运营内部标记：请说明此案件资金核对进度');
  await o.locator('#agentMessageForm button[type="submit"]').click();await o.waitForFunction(()=>!OceanV2.state.agentBusy&&OceanV2.state.activity.conversations.some(c=>c.message?.includes('运营内部标记')));
  assert.equal(await m.evaluate(()=>OceanV2.state.activity.conversations.some(c=>c.message?.includes('运营内部标记'))),false);
  assert.equal(await o.evaluate(()=>OceanV2.state.activity.conversations.some(c=>c.message?.includes('商户独有标记'))),false);
  await m.locator('#agentMessage').fill('结案后尚未发送的草稿');
  await m.goto(base+'/v2/merchant/cases/'+other.id);await loaded(m,other.id);
  assert.equal(await m.locator('#agentMessage').inputValue(),'');assert.equal(await m.evaluate(()=>OceanV2.state.activity.conversations.some(c=>c.message?.includes('商户独有标记'))),false);
  await m.goBack();await loaded(m,b.id);assert.equal(await m.locator('#agentMessage').inputValue(),'结案后尚未发送的草稿');
  await m.reload();await loaded(m,b.id);assert.equal(await m.locator('#agentMessage').inputValue(),'结案后尚未发送的草稿');
  report.checks.push('per-case / per-side conversations and draft restoration through navigation, back and reload');
  // Real browser disconnection and reconnect without a refresh.
  await cm.setOffline(true);await tab(o,'collaboration');v=await act(o,'COMMENT',{message:'离线期间的新进展，恢复网络后自动追平'});
  await cm.setOffline(false);start=Date.now();await checkSync(m,v,start);
  report.checks.push('offline reconnect catches up using durable cursor');
  await m.screenshot({path:'work/dual-surface-qa/merchant-desktop.png',fullPage:true});await o.screenshot({path:'work/dual-surface-qa/operations-desktop.png',fullPage:true});
  const mobile=await cm.newPage({viewport:{width:390,height:844}});await mobile.setViewportSize({width:390,height:844});await mobile.goto(base+'/v2/merchant/cases/'+b.id);await loaded(mobile,b.id);
  assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  await mobile.screenshot({path:'work/dual-surface-qa/merchant-mobile.png',fullPage:true});report.checks.push('390px merchant page has no horizontal overflow');
  assert.deepEqual(report.errors,[]);report.case_id=b.id;report.completed=true;
 } finally { fs.writeFileSync('work/dual-surface-qa/browser-report.json',JSON.stringify(report,null,2));await browser.close(); }
 console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
