const fs=require('node:fs');const vm=require('node:vm');const assert=require('node:assert/strict');
const root=require('node:path').resolve(__dirname,'..');
const example=JSON.parse(fs.readFileSync(__dirname+'/UI_EXAMPLE.json','utf8'));
const button={attributes:{},setAttribute(k,v){this.attributes[k]=v;}};
const panel={hidden:true,focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;}};
const body={innerHTML:''};const listeners={};
const elements={
 'risk-breakdown-panel':panel,'modal-body-content':body,'modal-work-id':{textContent:''},
 'projectDetailsModal':{},'btn-modal-report':{href:''}
};
let requested;
const context={document:{body:{dataset:{canAi:'true'}},getElementById:id=>elements[id]||null,
 querySelector:selector=>selector==='[data-risk-toggle]'?button:null,
 addEventListener:(name,fn)=>{listeners[name]=fn;}},
 bootstrap:{Modal:class{show(){}}},console,Number,String,URLSearchParams,
 fetch:url=>{requested=url;return Promise.resolve({json:()=>Promise.resolve({success:true,data:{
 project:{work_id:'R-05637',description:'Test work',risk_score:18,risk_level:'LOW',anomaly_detected:0,anomaly_score:1,estimated_cost:2696600000,actual_expenditure:852900000,status:'Ongoing'},
 nlp_matches:[],location_duplicates:[],reasons_list:[],risk_breakdown:example}})});}};
vm.createContext(context);vm.runInContext(fs.readFileSync(root+'/static/js/main.js','utf8'),context);
const html=context.riskBreakdownHTML(example);
assert.equal((html.match(/<tr>/g)||[]).length,8);
assert.equal((html.match(/>Awarded<\/span>/g)||[]).length,2);
assert.equal((html.match(/>Not awarded<\/span>/g)||[]).length,4);
assert.equal((html.match(/>Unavailable<\/span>/g)||[]).length,1);
assert.ok(html.includes('0 + 0 + 8 + 0 + 10 + 0 + 0 = 18 points'));
assert.ok(html.includes('0 / 10') && html.includes('10 / 20'));
const fraction=structuredClone(example);fraction.components.find(r=>r.key==='progress_gap').points=2.5;
fraction.uncapped_score=fraction.stored_score=fraction.calculated_score=20.5;
assert.ok(context.riskBreakdownHTML(fraction).includes('2.5 / 10'));
const capped=structuredClone(example);capped.components.forEach(r=>{r.points=r.maximum_points;r.status='Awarded';});
capped.uncapped_score=130;capped.calculated_score=capped.stored_score=100;capped.cap_adjustment=-30;
const cappedHtml=context.riskBreakdownHTML(capped);
assert.ok(cappedHtml.includes('130 -30 = 100'));
assert.ok(cappedHtml.includes('parameter maxima total 130'));
context.toggleRiskBreakdown();assert.equal(panel.hidden,false);assert.equal(button.attributes['aria-expanded'],'true');assert.ok(panel.focused);
context.toggleRiskBreakdown();assert.equal(panel.hidden,true);assert.equal(button.attributes['aria-expanded'],'false');
listeners.click({target:{closest:selector=>selector==='[data-risk-toggle]'?button:null}});
assert.equal(panel.hidden,false);
const malicious=structuredClone(example);malicious.components[0].value='<img src=x onerror=alert(1)>';
assert.ok(!context.riskBreakdownHTML(malicious).includes('<img'));
const score=context.riskScoreButton('R-05637',18,'bg-success');assert.ok(score.includes('data-risk-work-id="R-05637"'));assert.ok(score.includes('18/100'));
panel.hidden=true;
listeners.click({target:{closest:selector=>selector==='[data-risk-work-id]'?{dataset:{riskWorkId:'R-05637'}}:null}});
setImmediate(()=>{
 assert.equal(requested,'/api/projects/R-05637');assert.equal(panel.hidden,false);
 assert.ok(body.innerHTML.includes('How was 18 / 100 calculated?'));
 assert.equal(elements['btn-modal-report'].href,'/reports?work_id=R-05637');
 console.log('PASS: seven parameter rows, awarded/zero/unavailable states, exact sum, toggle/keyboard semantics, escaped evidence, and click-to-open score flow.');
});
