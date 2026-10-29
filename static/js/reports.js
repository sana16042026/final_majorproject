// reports.js - Project report generation & printable view

function reportEsc(v) {
    return String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

document.addEventListener('DOMContentLoaded', () => {
    loadSummaryData();

    document.getElementById('btn-generate-report').addEventListener('click', () => {
        const workId = document.getElementById('report-search-id').value.trim();
        if (workId) generateReport(workId);
        else showToast('Please enter a Work ID', 'warning');
    });

    document.getElementById('report-search-id').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const workId = e.target.value.trim();
            if (workId) generateReport(workId);
        }
    });
});

function loadSummaryData() {
    fetch('/api/reports/summary')
        .then(res => res.json())
        .then(data => {
            const s = data.summary;
            setText('summary-total-projects', (s.total_projects || 0).toLocaleString());
            setText('summary-high-risk', (s.high_risk_count || 0).toLocaleString());
            setText('summary-anomalies', (s.anomalies_count || 0).toLocaleString());
            setText('summary-sanctioned', formatINR(s.total_sanctioned));
            setText('summary-expenditure', formatINR(s.total_expenditure));
            setText('summary-nlp-count', s.nlp_similarity_count || 0);
            setText('summary-likely-duplicates', (s.likely_duplicates || 0).toLocaleString());
            setText('summary-possible-overlaps', (s.possible_overlaps || 0).toLocaleString());

            // Populate quick pills
            const pillsContainer = document.getElementById('quick-high-risk-pills');
            const hrList = data.high_risk_projects || [];
            if (hrList.length > 0) {
                pillsContainer.innerHTML = hrList.slice(0, 8).map(p => `
                    <button class="btn btn-sm btn-outline-danger py-0 px-2 small" onclick="generateReport('${reportEsc(p.work_id)}')">
                        ${reportEsc(p.work_id)}
                    </button>
                `).join('');

                // Auto-load first high risk project
                generateReport(new URLSearchParams(location.search).get('work_id') || hrList[0].work_id);
            } else {
                pillsContainer.innerHTML = `<span class="small text-muted">No high-risk projects.</span>`;
                const requested=new URLSearchParams(location.search).get('work_id');
                if(requested) generateReport(requested);
            }
        })
        .catch(err => console.error('Failed to load summary data:', err));
}

function generateReport(workId) {
    document.getElementById('report-search-id').value = workId;
    const bodyEl = document.getElementById('report-content-body');
    bodyEl.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Compiling official project audit report for ${reportEsc(workId)}...</p>
        </div>
    `;

    fetch(`/api/reports/project/${encodeURIComponent(workId)}`)
        .then(res => res.json())
        .then(res => {
            if (!res.success || !res.report) {
                bodyEl.innerHTML = `<div class="alert alert-danger py-4">Error: ${reportEsc(res.message || 'Report could not be generated.')}</div>`;
                return;
            }
            renderOfficialReport(res.report);
        })
        .catch(err => {
            bodyEl.innerHTML = `<div class="alert alert-danger py-4">Network error: ${reportEsc(err.message)}</div>`;
        });
}

function renderOfficialReport(reportData) {
    const p = reportData.project;
    const download = document.getElementById('download-project-report');
    if (download) { download.href='/api/reports/project/'+encodeURIComponent(p.work_id)+'/download'; download.classList.remove('d-none'); }
    const nlpMatches = reportData.nlp_matches || [];
    const reasons = reportData.reasons_list || [];
    const locationDuplicates = reportData.location_duplicates || [];

    document.getElementById('report-title-heading').textContent = `Official Audit Report: ${p.work_id}`;

    // Risk badge styling
    const riskBadgeClass = p.risk_level === 'HIGH' ? 'bg-danger text-white' :
                           p.risk_level === 'MEDIUM' ? 'bg-warning text-dark' : 'bg-success text-white';

    // NLP warning item (wording only, any location)
    let nlpSection = '';
    if (nlpMatches.length > 0) {
        nlpSection = nlpMatches.map(m => `
            <div class="p-2 border border-warning rounded bg-warning bg-opacity-10 mb-2 small">
                <i class="bi bi-link-45deg fs-6 text-warning"></i>
                <strong>Similar Wording Detected:</strong> Matches <strong>${reportEsc(m.matched_work_id)}</strong> with
                <strong>${(m.similarity_score * 100).toFixed(1)}%</strong> description similarity.
                <div class="text-muted mt-1 fst-italic">"${reportEsc(m.matched_description || '')}" (${reportEsc(m.matched_district || '')})</div>
            </div>
        `).join('');
    } else {
        nlpSection = `<div class="text-success small"><i class="bi bi-check-circle me-1"></i> No high-similarity road work description found.</div>`;
    }

    const reasonsListHtml = reasons.map(r => `<li class="mb-1">${reportEsc(r)}</li>`).join('') || '<li>Operating within normal project parameters.</li>';

    // 6. Location-aware duplicate check
    let duplicateSection;
    if (locationDuplicates.length > 0) {
        duplicateSection = locationDuplicates.map(d => `
            <div class="p-2 border rounded mb-2 small ${d.classification === 'Likely duplicate' ? 'border-danger bg-danger bg-opacity-10' : 'border-warning bg-warning bg-opacity-10'}">
                <span class="badge ${d.classification === 'Likely duplicate' ? 'bg-danger' : 'bg-warning text-dark'}">${reportEsc(d.classification)}</span>
                Matches <strong>${reportEsc(d.other_work_id)}</strong> (${reportEsc(d.other_district || '')}) &mdash;
                evidence score <strong>${Number(d.evidence_score).toFixed(0)}/100</strong>
                <div class="text-muted fst-italic mt-1">"${reportEsc(d.other_description || '')}"</div>
                <div class="mt-1"><i class="bi bi-info-circle me-1"></i>${reportEsc(d.evidence)}</div>
            </div>
        `).join('');
    } else {
        duplicateSection = `<div class="text-success small"><i class="bi bi-check-circle me-1"></i>
            No location-confirmed duplicate or overlapping project found (same district, backed by named place, road type, length and cost).</div>`;
    }

    const html = `
        <div class="alert alert-info small">Calculated delay: ${p.delay_days == null ? 'Unavailable' : reportEsc(p.delay_days)+' days'}. ${reportEsc(p.delay_basis)}.
        As of ${reportEsc(p.analysis_as_of)}. Expected: ${reportEsc(p.expected_completion_date || 'Unavailable')}; completed: ${reportEsc(p.completion_date || 'Unavailable')}.</div>
        <div class="report-paper">
            <!-- Header -->
            <div class="d-flex justify-content-between align-items-center border-bottom pb-3 mb-4">
                <div>
                    <h4 class="fw-bold mb-0 text-dark">MPLADS ROAD CONSTRUCTION AUDIT REPORT</h4>
                    <div class="text-muted small">Ministry of Statistics and Programme Implementation - Authority Portal</div>
                </div>
                <div class="text-end">
                    <span class="badge ${riskBadgeClass} fs-6 px-3 py-2">
                        RISK LEVEL: ${reportEsc(p.risk_level)}
                    </span>
                    <div class="small text-muted mt-1">Generated: ${new Date().toLocaleDateString('en-IN', { dateStyle: 'medium' })}</div>
                </div>
            </div>

            <!-- 1. Project Details -->
            <div class="card mb-4 border">
                <div class="card-header bg-light py-2">
                    <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-info-circle me-1"></i> 1. Project Basic Details</h6>
                </div>
                <div class="card-body p-3">
                    <div class="row g-3 small">
                        <div class="col-md-3"><strong>Work ID:</strong> <span class="badge bg-dark">${reportEsc(p.work_id)}</span></div>
                        <div class="col-md-3"><strong>Road Type:</strong> ${reportEsc(p.road_type)}</div>
                        <div class="col-md-3"><strong>Length:</strong> ${reportEsc(p.length_m)} meters</div>
                        <div class="col-md-3"><strong>Status:</strong> <span class="badge bg-secondary">${reportEsc(p.status)}</span></div>
                        <div class="col-md-12"><strong>Work Description:</strong> ${reportEsc(p.description)}</div>
                        <div class="col-md-4"><strong>State & District:</strong> ${reportEsc(p.district)}, ${reportEsc(p.state)}</div>
                        <div class="col-md-4"><strong>Constituency:</strong> ${reportEsc(p.constituency)} (${reportEsc(p.house)})</div>
                        <div class="col-md-4"><strong>MP Identifier:</strong> ${reportEsc(p.mp_id)}</div>
                    </div>
                </div>
            </div>

            <!-- 2. Financial Analysis & Progress Analysis -->
            <div class="row g-3 mb-4">
                <!-- Financial Analysis -->
                <div class="col-md-6">
                    <div class="card h-100 border">
                        <div class="card-header bg-light py-2">
                            <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-cash me-1"></i> 2. Financial Analysis</h6>
                        </div>
                        <div class="card-body p-3 small">
                            <table class="table table-sm table-borderless mb-0">
                                <tr><td>Estimated Cost:</td><td class="text-end fw-semibold">${formatINR(p.estimated_cost)}</td></tr>
                                <tr><td>Sanctioned Budget:</td><td class="text-end fw-semibold">${formatINR(p.sanctioned_amount)}</td></tr>
                                <tr><td>Agreement Amount:</td><td class="text-end">${formatINR(p.agreement_amount)}</td></tr>
                                <tr class="border-top fw-bold text-dark">
                                    <td>Actual Expenditure:</td><td class="text-end">${formatINR(p.actual_expenditure)}</td>
                                </tr>
                                <tr>
                                    <td>Cost Overrun:</td>
                                    <td class="text-end fw-bold ${p.cost_overrun_pct > 15 ? 'text-danger' : 'text-success'}">
                                        ${reportEsc(p.cost_overrun_pct)}%
                                    </td>
                                </tr>
                                <tr>
                                    <td>Bidders:</td>
                                    <td class="text-end">${reportEsc(p.number_of_bidders)} vendor(s) [${reportEsc(p.vendor_id)}]</td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Progress Analysis -->
                <div class="col-md-6">
                    <div class="card h-100 border">
                        <div class="card-header bg-light py-2">
                            <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-graph-up me-1"></i> 3. Progress Analysis</h6>
                        </div>
                        <div class="card-body p-3 small">
                            <div class="mb-2">
                                <div class="d-flex justify-content-between mb-1">
                                    <span>Physical Ground Progress:</span>
                                    <strong>${reportEsc(p.physical_progress_pct)}%</strong>
                                </div>
                                <div class="progress" style="height: 6px;">
                                    <div class="progress-bar bg-success" style="width: ${Number(p.physical_progress_pct) || 0}%"></div>
                                </div>
                            </div>
                            <div class="mb-3">
                                <div class="d-flex justify-content-between mb-1">
                                    <span>Financial Drawdown Progress:</span>
                                    <strong>${reportEsc(p.financial_progress_pct)}%</strong>
                                </div>
                                <div class="progress" style="height: 6px;">
                                    <div class="progress-bar bg-info" style="width: ${Number(p.financial_progress_pct) || 0}%"></div>
                                </div>
                            </div>
                            <table class="table table-sm table-borderless border-top pt-2 mb-0">
                                <tr>
                                    <td>Progress Gap (Fin - Phy):</td>
                                    <td class="text-end fw-bold ${p.physical_financial_gap_pct > 15 ? 'text-danger' : 'text-dark'}">
                                        ${reportEsc(p.physical_financial_gap_pct)}%
                                    </td>
                                </tr>
                                <tr>
                                    <td>Schedule Delay:</td>
                                    <td class="text-end fw-bold ${p.delay_days > 30 ? 'text-danger' : 'text-success'}">
                                        ${p.delay_days == null ? 'Unavailable' : reportEsc(p.delay_days)+' days'}
                                    </td>
                                </tr>
                            </table>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 4. ML Anomaly & NLP Similarity Analysis -->
            <div class="card mb-4 border">
                <div class="card-header bg-light py-2">
                    <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-cpu me-1"></i> 4. AI & Machine Learning Findings</h6>
                </div>
                <div class="card-body p-3">
                    <div class="row g-3">
                        <div class="col-md-6 border-end">
                            <h6 class="small fw-bold text-muted mb-2">Isolation Forest Anomaly Detection:</h6>
                            <div class="mb-2">
                                ${p.anomaly_detected == 1 ?
                                    '<span class="badge bg-danger p-2"><i class="bi bi-exclamation-triangle-fill me-1"></i> Anomaly Detected</span>' :
                                    '<span class="badge bg-success p-2"><i class="bi bi-check-circle me-1"></i> Normal Pattern</span>'}
                            </div>
                            <div class="small text-muted">
                                Anomaly Score: <strong>${(p.anomaly_score || 0).toFixed(4)}</strong> (Evaluated over 10 available source/derived numerical features; no fraud labels)
                            </div>
                        </div>
                        <div class="col-md-6">
                            <h6 class="small fw-bold text-muted mb-2">Description Similarity (wording only, any location):</h6>
                            ${nlpSection}
                        </div>
                    </div>
                </div>
            </div>

            <!-- 6. Location-aware Duplicate Check -->
            <div class="card mb-4 border">
                <div class="card-header bg-light py-2">
                    <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-geo-alt-fill me-1"></i> 5. Location-aware Duplicate & Overlap Check</h6>
                </div>
                <div class="card-body p-3">
                    ${duplicateSection}
                </div>
            </div>

            ${riskBreakdownHTML(reportData.risk_breakdown)}
            <!-- 7. Final Risk Score & Explainable Reasons -->
            <div class="card border border-2 ${p.risk_level === 'HIGH' ? 'border-danger' : p.risk_level === 'MEDIUM' ? 'border-warning' : 'border-success'} bg-white">
                <div class="card-header bg-light py-2 d-flex justify-content-between align-items-center">
                    <h6 class="mb-0 fw-bold text-uppercase small text-dark"><i class="bi bi-shield-check me-1"></i> 6. Risk Scoring & Explainable Decision Logic</h6>
                    <span class="fs-5 fw-bold ${p.risk_level === 'HIGH' ? 'text-danger' : p.risk_level === 'MEDIUM' ? 'text-warning' : 'text-success'}">
                        ${riskScoreButton(p.work_id,p.risk_score,p.risk_level==='HIGH'?'bg-danger':p.risk_level==='MEDIUM'?'bg-warning text-dark':'bg-success')}
                    </span>
                </div>
                <div class="card-body p-3">
                    <h6 class="small fw-bold text-dark mb-2">Flagged Decision Factors & Reasons:</h6>
                    <ul class="small mb-0 text-danger ps-3">
                        ${reasonsListHtml}
                    </ul>
                </div>
            </div>
        </div>
    `;

    document.getElementById('report-content-body').innerHTML = html;
}
