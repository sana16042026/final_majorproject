/* Clickable contextual evidence scores, with the server's saved point breakdown. */
(function () {
    const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    function duplicateEvidenceHTML(data) {
        return `<p class="fw-semibold">${esc(data.work_id_1)} ↔ ${esc(data.work_id_2)}</p>
        <p class="small">${esc(data.description_1)}<br>${esc(data.description_2)}</p>
        <p>${esc(data.location)} · <strong>${esc(data.classification)}</strong></p>
        <div class="table-responsive"><table class="table table-sm table-bordered align-middle"><thead><tr><th>Parameter</th><th>Evidence</th><th>Scoring rule</th><th>Points</th><th>Status</th></tr></thead><tbody>
        ${data.components.map(r=>`<tr><td>${esc(r.parameter)}</td><td>${esc(r.value)}</td><td>${esc(r.rule)}</td><td class="text-nowrap fw-bold">${Number(r.points)} / ${Number(r.maximum)}</td><td>${esc(r.status)}</td></tr>`).join('')}
        </tbody></table></div><p class="fw-bold">${data.components.map(r=>Number(r.points)).join(' + ')} = ${Number(data.total)} / 100</p>
        <p class="small text-muted">${esc(data.note)}</p>`;
    }
    window.duplicateEvidenceHTML=duplicateEvidenceHTML;
    let requestId=0;
    document.addEventListener('click',async event=>{
        const button=event.target.closest('[data-evidence-pair]');if(!button)return;
        const id=++requestId;
        let modal=document.getElementById('duplicateEvidenceModal');
        if(!modal){
            document.body.insertAdjacentHTML('beforeend',`<div class="modal fade" id="duplicateEvidenceModal" tabindex="-1" aria-labelledby="duplicateEvidenceTitle" aria-hidden="true"><div class="modal-dialog modal-xl modal-dialog-scrollable"><div class="modal-content"><div class="modal-header"><h5 class="modal-title" id="duplicateEvidenceTitle">How was the evidence score calculated?</h5><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div><div class="modal-body" id="duplicate-evidence-body"></div><div class="modal-footer"><button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button></div></div></div></div>`);
            modal=document.getElementById('duplicateEvidenceModal');
        }
        const body=document.getElementById('duplicate-evidence-body');body.innerHTML='<p role="status">Loading evidence…</p>';
        bootstrap.Modal.getOrCreateInstance(modal).show();
        try{
            const response=await fetch('/api/duplicates/'+encodeURIComponent(button.dataset.evidencePair)+'/evidence');
            const data=await response.json();if(id!==requestId)return;
            if(!response.ok)throw new Error(data.message||'Could not load evidence.');
            body.innerHTML=duplicateEvidenceHTML(data);
        }catch(error){if(id===requestId)body.innerHTML='<div class="alert alert-danger" role="alert">'+esc(error.message)+'</div>';}
    });
})();
