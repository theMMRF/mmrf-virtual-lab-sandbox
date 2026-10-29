// Verify the public saved-cohort UI in an isolated local browser profile.
import {chromium, expect} from '@playwright/test';
import {mkdir, writeFile} from 'node:fs/promises';

const origin=process.env.SANDBOX_ORIGIN || 'http://127.0.0.1:3080';
const url=new URL(origin);
if(url.protocol!=='http:' || !['localhost','127.0.0.1'].includes(url.hostname) || url.origin!==origin) {
  throw new Error('Saved-cohort browser checks require the local synthetic stack');
}
await mkdir('screenshots',{recursive:true});
let browser,page;
const errors=[],evidence=[],requests=[];
async function capture(name){await page.mouse.move(0,0);await page.screenshot({path:`screenshots/${name}.png`,fullPage:true});}
try {
  browser=await chromium.launch({headless:true});
  page=await browser.newPage({viewport:{width:1500,height:1050}});
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{
    if(request.url().includes('/protein-paint/'))requests.push({url:request.url(),method:request.method(),headers:request.headers(),body:request.postData()});
  });
  async function post(path,body){
    const response=await page.request.post(origin+path,{data:body});
    expect(response.ok(),path).toBe(true);
    const data=await response.json();
    expect(data.error,path).toBeUndefined();
    expect(data.errors,path).toBeUndefined();
    return data;
  }
  const mutated=await post('/analysis/v0/genomic/gene_cases',{
    cohort_filter:{},gene_filter:{and:[{in:{gene_id:['ENSG00000133703']}}]},ssm_filter:{},
  });
  const tested=[];
  let total;
  do {
    const data=await post('/analysis/v0/cases/',{filter:{in:{available_variation_data:['ssm']}},fields:['case_id'],size:1000,offset:tested.length});
    total=data.pagination.total;
    expect(data.data.length).toBeGreaterThan(0);
    tested.push(...data.data.map(row=>row.case_id));
  } while(tested.length<total);
  const carriers=new Set(mutated),testedIds=new Set(tested);
  expect(mutated.every(id=>testedIds.has(id))).toBe(true);
  const negative=tested.filter(id=>!carriers.has(id));
  expect(carriers.size).toBeGreaterThan(0);
  expect(negative.length).toBeGreaterThan(0);
  await page.goto(origin+'/?app=CohortBuilder',{waitUntil:'domcontentloaded'});
  await expect(page.getByText('Synthetic sandbox — all data is fabricated and has no clinical meaning.',{exact:true})).toBeVisible();
  for(const [name,ids] of [['API KRAS mutation present',mutated],['API KRAS mutation absent',negative]]) {
    await page.getByTestId('uploadButton').click();
    await page.getByRole('dialog').getByRole('textbox').fill(ids.join('\n'));
    await page.getByRole('dialog').getByRole('button',{name:'Submit',exact:true}).click();
    await page.getByPlaceholder('New Cohort Name').fill(name);
    await page.getByRole('dialog').getByRole('button',{name:'Save',exact:true}).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  }
  // Leave the negative cohort active: choosing saved cohorts must use each
  // saved selection rather than intersect the positive group with that scope.
  await page.goto(origin+'/?app=DE',{waitUntil:'domcontentloaded'});
  for(const [name,count] of [['API KRAS mutation absent',negative.length],['API KRAS mutation present',carriers.size]]) {
    await page.getByText('Add group',{exact:true}).click();
    await page.getByText('Cohort',{exact:true}).filter({visible:true}).click();
    if(name==='API KRAS mutation absent')await capture('saved-cohort-picker');
    await page.getByText(name,{exact:true}).last().click();
    await expect(page.locator('tr').filter({hasText:name})).toContainText(`${count} samples`);
  }
  for(const [cohort,oldName,newName] of [
    ['API KRAS mutation absent','New group','KRAS no mutation detected'],
    ['API KRAS mutation present','New group 1','KRAS mutated'],
  ]) {
    const row=page.locator('tr').filter({hasText:cohort});
    await row.getByText(oldName,{exact:true}).click();
    const input=row.locator('td').nth(1).locator('input');
    await input.fill(newName);
    await input.press('Enter');
  }
  const pendingPre=page.waitForResponse(r=>r.url().includes('/termdb/DE')&&r.request().postDataJSON()?.preAnalysis);
  await page.getByText('Submit (KRAS no mutation detected vs KRAS mutated)',{exact:true}).click();
  const preResponse=await pendingPre;
  const pre=await preResponse.json();
  evidence.push({request:preResponse.request().postDataJSON(),response:pre});
  expect(pre.data).toEqual({'KRAS no mutation detected':negative.length,'KRAS mutated':carriers.size});
  const preBody=preResponse.request().postDataJSON();
  expect(preBody.filter0).toBeNull();
  const sampleIds=preBody.samplelst.groups.flatMap(group=>group.values.map(value=>value.sampleId));
  const {mapping}=await post('/protein-paint/termdb',{genome:'hg38',dslabel:'MMRF',for:'convertSampleId',inputs:sampleIds});
  for(const group of preBody.samplelst.groups) {
    const ids=group.values.map(value=>mapping[value.sampleId]);
    expect([...ids].sort()).toEqual([...(group.name==='KRAS mutated'?mutated:negative)].sort());
  }
  await capture('saved-cohort-preanalysis');
  await page.getByText('Wilcoxon',{exact:true}).click();
  const pendingDE=page.waitForResponse(r=>r.url().includes('/termdb/DE')&&!r.request().postDataJSON()?.preAnalysis);
  await page.getByRole('button',{name:'Run Differential Gene Expression Analysis',exact:true}).click();
  const deResponse=await pendingDE;
  const de=await deResponse.json();
  evidence.push({request:deResponse.request().postDataJSON(),response:de});
  expect(de.error).toBeUndefined();
  expect(de.data.totalRows).toBeGreaterThan(0);
  expect(de.data.volcanoPng).toBeTruthy();
  await expect(page.getByText('Volcano',{exact:true})).toBeVisible({timeout:60000});
  await page.getByText('Show p-value table',{exact:true}).click();
  await page.locator('th').filter({hasText:'Adjusted p-value'}).getByRole('button').click();
  await capture('saved-cohort-de-result');
  await writeFile('screenshots/saved-cohort-requests.json',JSON.stringify(evidence,null,2));
  expect(errors).toEqual([]);
  console.log(`PASS: normal saved-cohort UI compares ${negative.length} vs ${carriers.size} API-defined cases; ${de.data.totalRows} expression genes, ${de.data.totalSignificantRows} significant`);
} catch(error) {
  await writeFile('screenshots/saved-cohort-failure-requests.json',JSON.stringify(requests,null,2));
  if(page&&!page.isClosed())await capture('saved-cohort-failure').catch(()=>{});
  throw error;
} finally {
  if(browser)await browser.close();
}
