/* Dedicated synthetic-instance browser acceptance. Never reads shared accounts.
 * NODE_PATH=<playwright node_modules> node scripts/verify_stage_browser.cjs <stage-manifest>
 * --exercise uploads v1/v2 and performs the real human-review form on this case.
 * It does NOT impersonate a real Feishu tenant or claim a timed stage rehearsal.
 */
const fs=require("node:fs"),path=require("node:path"),assert=require("node:assert/strict");
const {chromium}=require("playwright");
(async()=>{
 const manifestPath=path.resolve(process.argv[2]), m=JSON.parse(fs.readFileSync(manifestPath)), run=path.dirname(manifestPath);
 assert(m.synthetic_only && m.mode==="stage-demo" && m.tenant_acceptance==="NOT_RUN");
 const instance=path.resolve(run,"../.."), instanceManifest=JSON.parse(fs.readFileSync(path.join(instance,"instance.json")));
 assert.equal(m.instance_id,instanceManifest.id);
 const origin=new URL(m.merchant_url).origin;
 assert.equal(origin,`http://127.0.0.1:${instanceManifest.port}`,"Local acceptance must not mutate a live tenant");
 const accounts=JSON.parse(fs.readFileSync(path.join(instance,"private-accounts.json"))).accounts;
 const output=path.join(run,"browser-qa");fs.mkdirSync(output,{recursive:true,mode:0o700});
 const browser=await chromium.launch({headless:true,executablePath:process.env.STAGE_CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"});
 const errors=[],results=[],contexts=[];
 async function user(name,url){
  const ctx=await browser.newContext({viewport:{width:1920,height:1080}});contexts.push(ctx);
  const a=accounts.find(a=>a.user.username===name),response=await ctx.request.post(origin+"/api/v2/session/login",{data:{username:name,password:a.password}});
  assert(response.ok(),"Authentication failed");
  const page=await ctx.newPage();page.on("pageerror",e=>errors.push(e.message));
  await page.goto(url);await page.waitForSelector(".stage-heading h1");return page;
 }
 async function shot(page,name){
  for(const size of [{width:1920,height:1080},{width:1366,height:768}]){
   await page.setViewportSize(size);
   await page.screenshot({path:path.join(output,`${name}-${size.width}.png`),fullPage:true});
   const bounds=await page.evaluate(()=>({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,title:document.querySelector(".stage-heading h1").textContent}));
   results.push({screen:name,...bounds});
   assert(bounds.scrollWidth<=size.width,`${name}: horizontal overflow`);
   assert(bounds.scrollHeight<=size.height,`${name}: primary stage screen needs scrolling`);
  }
 }
 try{
  const merchant=await user("merchant-a",m.merchant_url),operator=await user("operator-a",m.operations_url);
  await shot(merchant,"merchant-initial");await shot(operator,"operator-initial");
  if(process.argv.includes("--exercise")){
   for(const [index,file] of m.materials.entries()){
    await merchant.locator('[data-action="REGISTER_EVIDENCE"]').click();
    const dialog=merchant.locator("#stageFilesDialog");await dialog.waitFor({state:"visible"});
    await dialog.locator('input[type="file"]').setInputFiles(file.path);
    await dialog.locator('.thread-upload button[type="submit"]').click();
    await dialog.waitFor({state:"hidden",timeout:30000});
    await merchant.waitForFunction(i=>document.querySelector(".stage-heading h1").textContent.includes(i===0?"缺少送达时间":"独立人工核验"),index);
    await operator.waitForFunction(i=>document.querySelector(".stage-heading h1").textContent.includes(i===0?"缺少送达时间":"独立人工核验"),index,{timeout:15000});
    await shot(merchant,`merchant-v${index+1}`);await shot(operator,`operator-v${index+1}`);
   }
   await operator.getByRole("button",{name:"打开原件 · 第 1 页"}).click();
   await operator.waitForFunction(()=>document.querySelector("#stageOriginal img").naturalWidth>0);
   await operator.screenshot({path:path.join(output,"original-preview.png")});
   await operator.getByRole("button",{name:"关闭原件"}).click();
   await operator.locator('[data-action="REVIEW_EVIDENCE_CONTENT"]').click();
   const form=operator.locator("#actionForm");await form.locator('[name="decision"]').selectOption("SUPPORTED");
   await form.locator('[name="reason"]').fill("合成场景浏览器验收：独立打开原件，核对第 1 页交易、金额、签收和送达时间。");
   await form.locator('[name="original_checked"]').check();
   const c=await operator.evaluate(()=>OceanV2.state.current);
   const evidence=c.evidence.find(e=>e.code==="fulfillment.proof_of_delivery");
   const facts=evidence.content_check.facts;
   await form.locator('[name="transaction_id"]').fill(c.transaction_id);
   await form.locator('[name="currency"]').fill(c.currency);
   await form.locator('[name="amount_minor"]').fill(String(c.amount_minor));
   await form.locator('[name="applicable_facts"]').fill(`recipient_confirmation: ${facts.recipient_confirmation}\ndelivered_at: ${facts.delivered_at}`);
   await form.locator('[name="locators"]').fill("page:1");
   await operator.locator("#confirmCheckbox").check();await operator.locator("#submitDialog").click();
   await operator.locator("#actionDialog").waitFor({state:"hidden",timeout:15000});
   await merchant.waitForFunction(()=>document.querySelector(".stage-heading h1").textContent.includes("材料已核验"),{timeout:15000});
   await shot(merchant,"merchant-verified");await shot(operator,"operator-verified");
   // Local UI acceptance only: Feishu callback behavior is exercised separately
   // by test_feishu_stage_submission.py, never portrayed as real tenant delivery.
   const result=await merchant.evaluate(async()=>{
    const c=OceanV2.state.current;
    return OceanV2.api("/commands",{method:"POST",body:JSON.stringify({command_id:crypto.randomUUID(),case_id:c.id,expected_revision:c.revision,action:"SUBMIT_EVIDENCE",confirmed:true,data:{}})});
   });
   assert.equal(result.case.work_status,"OP_REVIEW");
   await operator.waitForFunction(()=>document.querySelector(".stage-heading h1").textContent.includes("等待 OP 人工审核"),{timeout:15000});
   await merchant.waitForFunction(()=>document.querySelector(".stage-heading h1").textContent.includes("等待 OP 人工审核"),{timeout:15000});
   await shot(operator,"operator-submitted");await shot(merchant,"merchant-submitted");
  }
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(output,"acceptance.json"),JSON.stringify({kind:"LOCAL_BROWSER_ONLY",submission_transport:"AUTHENTICATED_HTTP_NOT_FEISHU",feishu_tenant:"NOT_RUN",errors,results},null,2));
  console.log(JSON.stringify({output,errors,results},null,2));
 }finally{for(const c of contexts)await c.close();await browser.close();}
})().catch(e=>{console.error(e.message);process.exitCode=1;});
