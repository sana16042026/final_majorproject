// dashboard.js - Fetch metrics and initialize Chart.js charts

let statusChartInstance = null;
let costChartInstance = null;
let riskChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    loadDashboardData();
});

function loadDashboardData() {
    fetch('/api/dashboard')
        .then(res => res.json())
        .then(data => {
            updateDashboardCards(data.cards);
            renderStatusChart(data.charts.status_chart);
            renderCostChart(data.charts.cost_comparison_chart);
            renderRiskChart(data.charts.risk_chart);
            renderHighRiskPreview(data.recent_high_risk);
        })
        .catch(err => {
            console.error('Error loading dashboard:', err);
            showToast('Failed to load dashboard data.', 'danger');
        });
}

function updateDashboardCards(cards) {
    if (!cards) return;
    document.getElementById('card-total-projects').textContent = (cards.total_projects || 0).toLocaleString();
    document.getElementById('card-completed-projects').textContent = (cards.completed_projects || 0).toLocaleString();
    document.getElementById('card-ongoing-projects').textContent = (cards.ongoing_projects || 0).toLocaleString();
    document.getElementById('card-delayed-projects').textContent = (cards.delayed_projects || 0).toLocaleString();
    document.getElementById('card-highrisk-projects').textContent = (cards.high_risk_projects || 0).toLocaleString();
    document.getElementById('card-total-expenditure').textContent = formatINR(cards.total_expenditure);
}

// Chart 1: Project Status (Completed, Ongoing, Delayed)
function renderStatusChart(statusData) {
    const ctx = document.getElementById('statusChart').getContext('2d');
    if (statusChartInstance) statusChartInstance.destroy();

    statusChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: statusData.labels,
            datasets: [{
                data: statusData.data,
                backgroundColor: ['#10b981', '#3b82f6', '#f59e0b'],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            }
        }
    });
}

// Chart 2: Estimated Cost vs Actual Expenditure
function renderCostChart(costData) {
    const ctx = document.getElementById('costComparisonChart').getContext('2d');
    if (costChartInstance) costChartInstance.destroy();

    // Shorten labels if necessary
    const shortLabels = costData.labels.map(l => l.replace(' Road', '').replace('Concrete', 'Conc.'));

    costChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: shortLabels,
            datasets: [
                {
                    label: 'Estimated (₹ Lakh)',
                    data: costData.estimated,
                    backgroundColor: '#93c5fd',
                    borderColor: '#3b82f6',
                    borderWidth: 1
                },
                {
                    label: 'Actual Exp (₹ Lakh)',
                    data: costData.actual,
                    backgroundColor: '#3b82f6',
                    borderColor: '#1d4ed8',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: '₹ in Lakhs', font: { size: 11 } }
                },
                x: {
                    ticks: { font: { size: 10 }, maxRotation: 20 }
                }
            },
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12 } }
            }
        }
    });
}

// Chart 3: Risk Distribution
function renderRiskChart(riskData) {
    const ctx = document.getElementById('riskDistributionChart').getContext('2d');
    if (riskChartInstance) riskChartInstance.destroy();

    riskChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: riskData.labels,
            datasets: [{
                data: riskData.data,
                backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            }
        }
    });
}

// Populate Top High Risk Projects Preview Table
function renderHighRiskPreview(projects) {
    const tbody = document.getElementById('high-risk-preview-tbody');
    if (!projects || projects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted py-3">No high-risk projects identified.</td></tr>`;
        return;
    }

    tbody.innerHTML = projects.map(p => {
        const primaryReason = (p.risk_reason || '').split('|')[0] || 'High risk factors detected';
        return `
            <tr>
                <td class="fw-bold"><span class="badge bg-dark">${p.work_id}</span></td>
                <td class="text-truncate" style="max-width: 280px;" title="${p.description}">${p.description}</td>
                <td><span class="badge bg-light text-dark border">${p.road_type}</span></td>
                <td><small class="text-muted">${p.district}, ${p.state}</small></td>
                <td class="fw-semibold">${formatINR(p.actual_expenditure)}</td>
                <td>
                    ${riskScoreButton(p.work_id,p.risk_score,'bg-danger')}
                </td>
                <td class="small text-danger text-truncate" style="max-width: 250px;" title="${p.risk_reason}">
                    <i class="bi bi-exclamation-circle-fill me-1"></i>${primaryReason}
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
