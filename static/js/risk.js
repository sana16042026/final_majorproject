// risk.js - Risk analysis breakdown & dynamic alerts

document.addEventListener('DOMContentLoaded', () => {
    loadRiskData();
    loadAlertsData();

    document.getElementById('btn-rerun-nlp').addEventListener('click', rerunNLP);
    document.getElementById('btn-rerun-ml').addEventListener('click', rerunML);
});

function loadRiskData() {
    fetch('/api/risk-analysis')
        .then(res => res.json())
        .then(data => {
            const counts = data.counts || {};
            document.getElementById('risk-high-count').textContent = counts.high_count || 0;
            document.getElementById('risk-med-count').textContent = counts.med_count || 0;
            document.getElementById('risk-low-count').textContent = counts.low_count || 0;

            renderHighRiskTable(data.high_risk_projects);
        })
        .catch(err => {
            console.error('Failed to load risk data:', err);
            showToast('Failed to load risk analysis data.', 'danger');
        });
}

function renderHighRiskTable(projects) {
    const tbody = document.getElementById('high-risk-tbody');
    if (!projects || projects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-muted">No high-risk projects currently detected.</td></tr>`;
        return;
    }

    tbody.innerHTML = projects.map(p => {
        const reasonsList = (p.risk_reason || '').split('|').map(r => r.trim()).filter(Boolean);
        const reasonBadge = reasonsList.length > 0 ? reasonsList[0] : 'High risk pattern';

        return `
            <tr>
                <td class="fw-bold"><span class="badge bg-dark">${p.work_id}</span></td>
                <td class="text-truncate" style="max-width: 220px;" title="${p.description}">${p.description}</td>
                <td><small class="text-muted">${p.district}, ${p.state}</small></td>
                <td class="fw-semibold">${formatINR(p.actual_expenditure)}</td>
                <td class="${p.cost_overrun_pct > 15 ? 'text-danger fw-bold' : 'text-muted'}">${p.cost_overrun_pct}%</td>
                <td class="${p.delay_days > 45 ? 'text-danger fw-bold' : 'text-muted'}">${p.delay_days == null ? 'Unavailable' : p.delay_days+' d'}</td>
                <td class="${p.physical_financial_gap_pct > 15 ? 'text-danger fw-bold' : 'text-muted'}">${p.physical_financial_gap_pct}%</td>
                <td><span class="badge bg-danger fs-6">${p.risk_score} / 100</span></td>
                <td class="small text-danger text-truncate" style="max-width: 260px;" title="${p.risk_reason}">
                    <i class="bi bi-exclamation-triangle-fill me-1"></i>${reasonBadge}
                </td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-primary" onclick="viewProjectDetails('${p.work_id}')">
                        <i class="bi bi-eye"></i> Details
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function loadAlertsData() {
    fetch('/api/alerts')
        .then(res => res.json())
        .then(data => {
            const alerts = data.alerts || [];
            document.getElementById('alerts-count-badge').textContent = alerts.length;
            renderAlertsList(alerts);
        })
        .catch(err => {
            console.error('Failed to load alerts:', err);
            document.getElementById('alerts-container').innerHTML = `<div class="alert alert-danger">Error loading alerts: ${err.message}</div>`;
        });
}

function renderAlertsList(alerts) {
    const container = document.getElementById('alerts-container');
    if (!alerts || alerts.length === 0) {
        container.innerHTML = `<div class="text-center py-4 text-muted">No active alerts at this time.</div>`;
        return;
    }

    container.innerHTML = alerts.map(a => {
        const borderClass = a.severity === 'danger' ? 'border-danger' :
                            a.severity === 'warning' ? 'border-warning' : 'border-info';

        const iconClass = a.type === 'HIGH_RISK' ? 'bi-exclamation-octagon-fill text-danger' :
                          a.type === 'ML_ANOMALY' ? 'bi-cpu-fill text-danger' :
                          a.type === 'NLP_SIMILARITY' ? 'bi-link-45deg text-warning' :
                          a.type === 'PROGRESS_GAP' ? 'bi-graph-down-arrow text-warning' : 'bi-clock-history text-info';

        return `
            <div class="card mb-2 border-start border-4 ${borderClass} shadow-sm">
                <div class="card-body p-3 d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-start gap-3">
                        <i class="bi ${iconClass} fs-3 mt-1"></i>
                        <div>
                            <div class="d-flex align-items-center gap-2 mb-1">
                                <span class="badge bg-${a.severity} text-${a.severity === 'warning' ? 'dark' : 'white'}">${a.badge}</span>
                                <h6 class="mb-0 fw-bold text-dark">${a.title}</h6>
                            </div>
                            <p class="small text-muted mb-0">${a.message}</p>
                        </div>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-secondary" onclick="viewProjectDetails('${a.work_id}')">
                            <i class="bi bi-eye"></i> Investigate
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function rerunNLP() {
    const btn = document.getElementById('btn-rerun-nlp');
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Running TF-IDF...`;

    fetch('/api/run-nlp', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            showToast(data.message, 'success');
            loadAlertsData();
            loadRiskData();
        })
        .catch(err => showToast(`Error: ${err.message}`, 'danger'))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-fonts me-1"></i> Re-run NLP Description Similarity`;
        });
}

function rerunML() {
    const btn = document.getElementById('btn-rerun-ml');
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span> Running Isolation Forest...`;

    fetch('/api/run-ml', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            showToast(data.message, 'success');
            loadAlertsData();
            loadRiskData();
        })
        .catch(err => showToast(`Error: ${err.message}`, 'danger'))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = `<i class="bi bi-diagram-3-fill me-1"></i> Re-run Isolation Forest (ML)`;
        });
}
