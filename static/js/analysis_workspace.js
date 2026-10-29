// Shared read-only result lists; existing engines and processing pipeline are unchanged.
document.addEventListener('DOMContentLoaded',()=>{
    const mode=document.querySelector('[data-analysis-mode]').dataset.analysisMode;
    const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const actions=id=>`<button class="btn btn-sm btn-outline-primary" data-work-id="${esc(id)}">Details</button> <a class="btn btn-sm btn-outline-secondary" href="/reports?work_id=${encodeURIComponent(id)}">Generate Report</a>`;
    let page=1,pages=1,timer,requestNumber=0;
    async function load(next=1){
        page=next;const current=++requestNumber;
        const query=new URLSearchParams({page,limit:25,search:document.getElementById('module-search').value.trim()});
        if(mode==='financial')query.set('kind',document.getElementById('module-kind').value);
        const body=document.getElementById('module-tbody');body.innerHTML='<tr><td colspan="7">Loading results…</td></tr>';
        try{
            const response=await fetch((mode==='financial'?'/api/financial-analysis/projects':'/api/similarity/projects')+'?'+query);
            const data=await response.json();if(current!==requestNumber)return;
            if(!response.ok||data.success===false)throw new Error(data.message||'Could not load results.');
            pages=data.total_pages;page=data.page;document.getElementById('module-total').textContent=Number(data.total).toLocaleString();
            document.getElementById('module-info').textContent=`Page ${page} of ${pages} · ${Number(data.total).toLocaleString()} results`;
            document.getElementById('module-prev').disabled=page<=1;document.getElementById('module-next').disabled=page>=pages;
            const rows=mode==='financial'?data.projects:data.pairs;
            body.innerHTML=rows.map(p=>mode==='financial'?`<tr><td>${esc(p.work_id)}</td><td>${esc(p.description)}</td><td>${esc(p.district)}, ${esc(p.state)}</td><td>${formatINR(p.actual_expenditure)}</td><td>${Number(p.anomaly_score).toFixed(4)}</td><td><span class="badge ${p.anomaly_detected?'bg-danger':'bg-success'}">${p.anomaly_detected?'Anomaly flagged':'Not flagged'}</span></td><td>${actions(p.work_id)}</td></tr>`:
                `<tr><td>${esc(p.work_id_1)} ↔ ${esc(p.work_id_2)}</td><td>${esc(p.description_1)}<hr>${esc(p.description_2)}</td><td>${esc(p.district_1)}, ${esc(p.state_1)}<hr>${esc(p.district_2)}, ${esc(p.state_2)}</td><td>${(Number(p.similarity_score)*100).toFixed(2)}%</td><td>${actions(p.work_id_1)}<hr>${actions(p.work_id_2)}</td></tr>`).join('')||'<tr><td colspan="7">No matching results.</td></tr>';
            const summary=document.getElementById('module-summary');
            if(mode==='financial')summary.innerHTML=Object.entries({Analysed:data.summary.analysed,'Flagged anomalies':data.summary.flagged,'Not flagged':data.summary.normal}).map(([label,value])=>`<div class="col-md-4"><div class="card p-3"><span>${label}</span><strong class="fs-3">${Number(value).toLocaleString()}</strong></div></div>`).join('')+'<p class="small text-muted">ML scores are normalized model scores, not fraud probabilities. This review queue is separate from combined risk categories.</p>';
            else summary.innerHTML='<p class="small text-muted">Wording-only candidates use cosine similarity ≥70%; at most 1,000 strongest pairs are stored. Use Contextual Duplicate Detection for location and other matching evidence.</p>';
        }catch(error){body.innerHTML='<tr><td colspan="7" class="text-danger">'+esc(error.message)+'</td></tr>';}
    }
    if(mode!=='risk'){
        document.getElementById('module-prev').onclick=()=>{if(page>1)load(page-1);};
        document.getElementById('module-next').onclick=()=>{if(page<pages)load(page+1);};
        document.getElementById('module-search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>load(1),350);};
        document.getElementById('module-kind')?.addEventListener('change',()=>load(1));
        document.getElementById('module-tbody').onclick=e=>{const button=e.target.closest('[data-work-id]');if(button)viewProjectDetails(button.dataset.workId);};
        load(1);
    }
    document.getElementById('module-refresh')?.addEventListener('click',async function(){
        this.disabled=true;this.textContent='Refreshing…';
        try{const response=await fetch('/api/run-ml',{method:'POST'});const data=await response.json();if(!response.ok||!data.success)throw new Error(data.message||'Refresh failed');location.reload();}
        catch(error){showToast(error.message,'danger');this.disabled=false;this.textContent='Refresh Analysis';}
    });
});
