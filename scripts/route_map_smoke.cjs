// Run in Projects' installed Playwright environment against a staged or public release.
const { createRequire } = require("node:module");
const { chromium } = createRequire(process.cwd() + "/package.json")("playwright");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const [url,stage] = process.argv.slice(2);
(async()=>{
 const browser=await chromium.launch();
 try {
  for(const width of [390,1280]) {
   const ctx=await browser.newContext({viewport:{width,height:800}});
   if(stage){
    const headers=execFileSync("vercel",["curl","/?x-vercel-set-bypass-cookie=true","--deployment",url,"--scope=brycepjs-projects","--","--head"],{stdio:["ignore","pipe","pipe"]}).toString();
    const cookies=[...headers.matchAll(/^set-cookie:\s*([^=;\s]+)=([^;\r\n]*)/gim)].map(m=>({name:m[1],value:m[2],url}));
    await ctx.addCookies(cookies);
   }
   const res=await ctx.request.get(url+"/data/safe-routes/safe-route-stress-crossings.geojson");
   assert.equal(res.status(),200);
   const crossings=(await res.json()).features;
   const example=crossings.find(f=>f.properties.stress==="higher")||crossings.find(f=>f.properties.stress==="lower");
   assert.ok(example,"The proposed release has no modeled crossing to verify");
   const page=await ctx.newPage(); const errors=[];
   page.on("pageerror",e=>errors.push(e.message));
   let downloads=0;page.on("request",r=>{if(r.url().includes("/safe-route-stress-"))downloads++});
   await page.goto(url+"/maps/safe-routes");
   const toggle=page.getByRole("switch",{name:"Bike riding conditions"});
   await toggle.waitFor(); assert.equal(await toggle.getAttribute("aria-checked"),"false");assert.equal(downloads,0);
   await page.getByRole("button",{name:example.properties.schoolName,exact:true}).click();
   await toggle.click();await page.locator('[data-map-ready="true"]').waitFor({timeout:45000});
   await page.getByText("Browse crossings for "+example.properties.schoolName,{exact:true}).click();
   const description=(example.properties.stress==="higher"?"Busier":"Calmer")+" crossing"+(example.properties.street?" · "+example.properties.street:"")+(example.properties.crossStreet?" at "+example.properties.crossStreet:"");
   await page.getByRole("button",{name:description,exact:true}).first().click();
   const card=page.getByRole("region",{name:"Riding conditions details"});
   await card.getByText(description,{exact:true}).first().waitFor();
   await card.getByRole("button",{name:"Close"}).click();await page.locator(".maplibregl-canvas").click();await card.getByText(description,{exact:true}).first().waitFor();
   assert.equal(downloads,2);assert.deepEqual(errors,[]);
   await page.goto(url+"/data-hub");
   for(const name of ["Riding conditions along routes (GeoJSON)","Riding conditions at crossings (GeoJSON)"]) await page.getByRole("link",{name}).waitFor();
   await ctx.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
