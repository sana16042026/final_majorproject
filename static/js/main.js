// main.js - Common utilities and Global Project Details Modal

// Format currency in Indian Rupees
function formatINR(amount) {
    if (amount === null || amount === undefined || isNaN(amount)) return 'Unavailable';
    const num = Number(amount);
    if (num >= 10000000) {
        return '₹' + (num / 10000000).toFixed(2) + ' Cr';
    } else if (num >= 100000) {
        return '₹' + (num / 100000).toFixed(2) + ' Lakh';
    }
    return '₹' + num.toLocaleString('en-IN');
}

// Show Toast Alert
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const bgClass = type === 'success' ? 'bg-success text-white' :
                    type === 'danger' ? 'bg-danger text-white' :
                    type === 'warning' ? 'bg-warning text-dark' : 'bg-primary text-white';

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center ${bgClass} border-0 shadow-sm mb-2`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');

    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close ${type !== 'warning' ? 'btn-close-white' : ''} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 4500 });
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
}

// Global View Project Details Modal Handler
function viewProjectDetails(workId) {
    const modalEl = document.getElementById('projectDetailsModal');
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl);
    document.getElementById('modal-work-id').textContent = workId;
    const bodyEl = document.getElementById('modal-body-content');

    bodyEl.innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Fetching project details from database...</p>
        </div>
    `;
    modal.show();

    fetch(`/api/projects/${workId}`)
        .then(res => res.json())
        .then(res => {
            if (!res.success || !res.data) {
                bodyEl.innerHTML = `<div class="alert alert-danger">Error: ${res.message || 'Project not found.'}</div>`;
                return;
            }
            renderProjectModalContent(res.data);
        })
        .catch(err => {
            bodyEl.innerHTML = `<div class="alert alert-danger">Network error: ${err.message}</div>`;
        });
}

function renderProjectModalContent(data) {
    const p = data.project;
    const nlpMatches = data.nlp_matches || [];
    const reasons = data.reasons_list || [];

    // Role-based visibility: base.html sets data-can-ai on <body>.
    // Vendors and citizens get no risk / ML / NLP data from the server.
    const canSeeAI = document.body.dataset.canAi !== 'false';

    // Badges
    const riskBadgeClass = p.risk_level === 'HIGH' ? 'badge-risk-high' :
                           p.risk_level === 'MEDIUM' ? 'badge-risk-med' : 'badge-risk-low';

    const statusBadge = p.status === 'Completed' ? '<span class="badge bg-success">Completed</span>' :
                        p.status === 'Delayed' ? '<span class="badge bg-danger">Delayed</span>' :
                        '<span class="badge bg-primary">Ongoing</span>';

    const mlBadge = p.anomaly_detected == 1 ?
        '<span class="badge bg-danger"><i class="bi bi-exclamation-triangle-fill me-1"></i> Anomaly Detected</span>' :
        '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i> Normal Pattern</span>';

    // Risk badge in the header (AI roles only)
    const riskHeaderHtml = canSeeAI ? `
                            <div class="mt-2">
                                <span class="${riskBadgeClass}"><i class="bi bi-shield-fill me-1"></i>${p.risk_level} RISK</span>
                            </div>` : '';

    // Vendor details (hidden for citizens: the server removes vendor_id for them)
    const vendorHtml = p.vendor_id !== undefined ?
        `<div class="col-md-4"><strong>Vendor ID:</strong> ${p.vendor_id} (${p.number_of_bidders ?? 'Unavailable'} bidders)</div>` : '';

    // NLP similarity section
    let nlpHtml = '';
    if (nlpMatches.length > 0) {
        const topMatch = nlpMatches[0];
        nlpHtml = `
            <div class="alert alert-warning p-2 mb-2 d-flex align-items-center justify-content-between">
                <div>
                    <i class="bi bi-link-45deg fs-5 me-1 text-warning"></i>
                    <strong>Similar Project Detected:</strong>
                    <span class="badge bg-dark">${p.work_id}</span> ↔
                    <span class="badge bg-secondary cursor-pointer" onclick="viewProjectDetails('${topMatch.matched_work_id}')" style="cursor:pointer;" title="Click to view">${topMatch.matched_work_id}</span>
                    <span class="ms-2 text-dark font-monospace fw-bold">Similarity: ${(topMatch.similarity_score * 100).toFixed(1)}%</span>
                </div>
            </div>
        `;
    } else {
        nlpHtml = `<div class="text-muted small">No duplicate or high-similarity description detected.</div>`;
    }

    // Reasons HTML
    let reasonsHtml = reasons.map(r => `<li class="mb-1">${r}</li>`).join('');
    if (!reasonsHtml) {
        reasonsHtml = '<li>Operating within normal parameters.</li>';
    }

    // Predicted outcome learned from the uploaded dataset (AI roles only)
    const pr = data.prediction;
    const predictionHtml = pr ? `
                    <div class="mb-3 p-2 border rounded bg-light">
                        <div class="small fw-bold text-dark mb-2">
                            <i class="bi bi-graph-up-arrow me-1"></i> Observed Outcome Estimate
                            <span class="fw-normal text-muted">(cross-validated on this dataset; not final completion forecasts)</span>
                        </div>
                        <div class="row g-2 small">
                            <div class="col-md-6">
                                Delay: <strong>${Number(pr.predicted_delay_days).toFixed(1)} days</strong>
                                <span class="text-muted">(recorded: ${p.delay_days ?? 'Unavailable'} days)</span>
                                ${pr.delay_likely == 1 ? '<span class="badge bg-danger ms-1">Delay likely</span>' : '<span class="badge bg-success ms-1">On track</span>'}
                            </div>
                            <div class="col-md-6">
                                Cost overrun: <strong>${Number(pr.predicted_overrun_pct).toFixed(1)}%</strong>
                                <span class="text-muted">(recorded: ${p.cost_overrun_pct}%)</span>
                                ${pr.overrun_likely == 1 ? '<span class="badge bg-warning text-dark ms-1">Overrun likely</span>' : '<span class="badge bg-success ms-1">Within range</span>'}
                            </div>
                        </div>
                    </div>` : '';

    // Location-aware duplicate / overlap matches (AI roles only)
    const locDups = data.location_duplicates || [];
    const locationDupHtml = locDups.length > 0 ? `
                    <div class="mb-3 p-2 border rounded bg-light">
                        <div class="small fw-bold text-dark mb-2">
                            <i class="bi bi-geo-alt-fill me-1"></i> Location-aware Duplicate Check
                            <span class="fw-normal text-muted">(same district, backed by place / road type / length / cost)</span>
                        </div>
                        ${locDups.map(d => `
                            <div class="small mb-1">
                                <span class="badge ${d.classification === 'Likely duplicate' ? 'bg-danger' : 'bg-warning text-dark'}">${d.classification}</span>
                                <span class="badge bg-secondary" style="cursor:pointer;" title="Click to view" onclick="viewProjectDetails('${d.other_work_id}')">${d.other_work_id}</span>
                                <span class="fw-bold ms-1">${Number(d.evidence_score).toFixed(0)}/100</span>
                                <div class="text-muted ms-1">${d.evidence}</div>
                            </div>`).join('')}
                    </div>` : '';

    // AI / Machine Learning & NLP Analysis card (AI roles only)
    const aiSectionHtml = canSeeAI ? `
            <!-- AI / Machine Learning & NLP Analysis -->
            <div class="col-12">
                <div class="card p-3 border-primary border-opacity-25 bg-white">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h6 class="text-uppercase text-primary small fw-bold mb-0">
                            <i class="bi bi-cpu-fill me-1"></i> AI & Machine Learning Analysis
                        </h6>
                        <div class="d-flex align-items-center gap-2">
                            <span class="small text-muted">Risk Score:</span>
                            <span class="badge ${p.risk_score >= 70 ? 'bg-danger' : p.risk_score >= 40 ? 'bg-warning text-dark' : 'bg-success'} fs-6">
                                ${p.risk_score} / 100
                            </span>
                        </div>
                    </div>

                    <div class="row g-2 mb-3">
                        <div class="col-md-6">
                            <div class="p-2 border rounded bg-light">
                                <div class="small text-muted mb-1">Machine Learning (${p.model_name || 'Isolation Forest'}):</div>
                                ${mlBadge}
                                <span class="small ms-2 text-muted">Score: ${(p.anomaly_score || 0).toFixed(3)}</span>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="p-2 border rounded bg-light">
                                <div class="small text-muted mb-1">Description Similarity (wording only):</div>
                                ${nlpHtml}
                            </div>
                        </div>
                    </div>

${predictionHtml}
${locationDupHtml}
                    <div>
                        <div class="small fw-bold text-dark mb-1">Risk Reasons & Explanation:</div>
                        <ul class="small mb-0 text-danger ps-3">
                            ${reasonsHtml}
                        </ul>
                    </div>
                </div>
            </div>` : '';

    const html = `
        <div class="row g-3">
            <!-- Basic Information -->
            <div class="col-12"><div class="alert alert-info small">
            Delay: <strong>${p.delay_days == null ? 'Unavailable' : p.delay_days+' days'}</strong><br>
            Expected completion: ${p.expected_completion_date ? new Date(p.expected_completion_date).toLocaleDateString('en-IN') : 'Unavailable'};
            actual completion: ${p.completion_date ? new Date(p.completion_date).toLocaleDateString('en-IN') : 'Unavailable'}<br>
            Basis: ${p.delay_basis || 'Unavailable'}. Calculated as of ${p.analysis_as_of ? new Date(p.analysis_as_of).toLocaleDateString('en-IN') : 'Unavailable'} (India time).
            </div></div>
            <div class="col-12">
                <div class="card bg-light border-0 p-3 mb-2">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <h6 class="text-uppercase text-muted small fw-bold mb-1">Basic Information</h6>
                            <h5 class="fw-bold mb-1">${p.work_id} - ${p.description}</h5>
                            <div class="text-muted small">
                                <span class="me-3"><i class="bi bi-geo-alt me-1"></i>${p.district}, ${p.state}</span>
                                <span class="me-3"><i class="bi bi-building me-1"></i>${p.constituency} (${p.house})</span>
                                <span><i class="bi bi-person me-1"></i>${p.mp_id}</span>
                            </div>
                        </div>
                        <div class="text-end">
                            ${statusBadge}${riskHeaderHtml}
                        </div>
                    </div>
                    <div class="row mt-3 pt-2 border-top g-2 small">
                        <div class="col-md-4"><strong>Road Type:</strong> ${p.road_type}</div>
                        <div class="col-md-4"><strong>Length:</strong> ${p.length_m} meters</div>
                        ${vendorHtml}
                    </div>
                </div>
            </div>

            <!-- Financial Information -->
            <div class="col-md-6">
                <div class="card h-100 p-3">
                    <h6 class="text-uppercase text-primary small fw-bold mb-3">
                        <i class="bi bi-cash-stack me-1"></i> Financial Information
                    </h6>
                    <table class="table table-sm table-borderless small mb-0">
                        <tr>
                            <td class="text-muted">Estimated Cost:</td>
                            <td class="text-end fw-semibold">${formatINR(p.estimated_cost)}</td>
                        </tr>
                        <tr>
                            <td class="text-muted">Sanctioned Amount:</td>
                            <td class="text-end fw-semibold">${formatINR(p.sanctioned_amount)}</td>
                        </tr>
                        <tr>
                            <td class="text-muted">Agreement Amount:</td>
                            <td class="text-end">${formatINR(p.agreement_amount)}</td>
                        </tr>
                        <tr class="border-top">
                            <td class="fw-bold text-dark">Actual Expenditure:</td>
                            <td class="text-end fw-bold text-dark">${formatINR(p.actual_expenditure)}</td>
                        </tr>
                        <tr>
                            <td class="text-muted">Cost Overrun:</td>
                            <td class="text-end fw-bold ${p.cost_overrun_pct > 15 ? 'text-danger' : 'text-success'}">
                                ${p.cost_overrun_pct > 0 ? '+' : ''}${p.cost_overrun_pct}%
                            </td>
                        </tr>
                    </table>
                </div>
            </div>

            <!-- Progress Information -->
            <div class="col-md-6">
                <div class="card h-100 p-3">
                    <h6 class="text-uppercase text-primary small fw-bold mb-3">
                        <i class="bi bi-clock-history me-1"></i> Progress Information
                    </h6>
                    <div class="mb-2">
                        <div class="d-flex justify-content-between small mb-1">
                            <span>Physical Progress:</span>
                            <span class="fw-bold">${p.physical_progress_pct}%</span>
                        </div>
                        <div class="progress" style="height: 7px;">
                            <div class="progress-bar bg-success" style="width: ${p.physical_progress_pct}%"></div>
                        </div>
                    </div>

                    <div class="mb-2">
                        <div class="d-flex justify-content-between small mb-1">
                            <span>Financial Progress:</span>
                            <span class="fw-bold">${p.financial_progress_pct}%</span>
                        </div>
                        <div class="progress" style="height: 7px;">
                            <div class="progress-bar bg-info" style="width: ${p.financial_progress_pct}%"></div>
                        </div>
                    </div>

                    <table class="table table-sm table-borderless small mb-0 mt-3 pt-2 border-top">
                        <tr>
                            <td class="text-muted">Progress Gap (Fin - Phy):</td>
                            <td class="text-end fw-bold ${p.physical_financial_gap_pct > 15 ? 'text-danger' : 'text-secondary'}">
                                ${p.physical_financial_gap_pct}%
                            </td>
                        </tr>
                        <tr>
                            <td class="text-muted">Schedule Delay:</td>
                            <td class="text-end fw-bold ${p.delay_days > 30 ? 'text-danger' : 'text-success'}">
                                ${p.delay_days ?? 'Unavailable'} days
                            </td>
                        </tr>
                    </table>
                </div>
            </div>
${aiSectionHtml}
        </div>
    `;

    document.getElementById('modal-body-content').innerHTML = html;
}
