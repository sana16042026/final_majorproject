// projects.js - Filterable, searchable & paginated road construction projects

let currentPage = 1;
let currentLimit = 50;
let totalProjects = 0;
let totalPages = 1;

document.addEventListener('DOMContentLoaded', () => {
    loadFilterOptions();
    readUrlParams();
    fetchProjects(1);

    // Event listeners
    document.getElementById('filter-search').addEventListener('input', debounce(() => fetchProjects(1), 350));

    // State -> District cascade: only districts of the chosen state are listed
    document.getElementById('filter-state').addEventListener('change', () => {
        document.getElementById('filter-district').value = '';
        loadDistricts(document.getElementById('filter-state').value);
        fetchProjects(1);
    });

    document.getElementById('filter-district').addEventListener('change', () => fetchProjects(1));
    document.getElementById('filter-risk').addEventListener('change', () => fetchProjects(1));
    document.getElementById('filter-status').addEventListener('change', () => fetchProjects(1));

    document.getElementById('btn-reset-filters').addEventListener('click', () => {
        document.getElementById('filter-search').value = '';
        document.getElementById('filter-state').value = '';
        document.getElementById('filter-district').value = '';
        document.getElementById('filter-risk').value = '';
        document.getElementById('filter-status').value = '';
        loadDistricts('');
        fetchProjects(1);
    });

    document.getElementById('btn-prev-page').addEventListener('click', () => {
        if (currentPage > 1) {
            fetchProjects(currentPage - 1);
        }
    });

    document.getElementById('btn-next-page').addEventListener('click', () => {
        if (currentPage < totalPages) {
            fetchProjects(currentPage + 1);
        }
    });
});

function readUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const risk = params.get('risk_level');
    const status = params.get('status');
    const search = params.get('search');
    if (risk) document.getElementById('filter-risk').value = risk.toUpperCase();
    if (status) document.getElementById('filter-status').value = status;
    if (search) document.getElementById('filter-search').value = search;
}

// Fill a <select>, keeping its first "All ..." option
function fillSelectOptions(select, values) {
    select.options.length = 1;
    (values || []).forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v;
        select.appendChild(opt);
    });
}

function loadFilterOptions() {
    fetch('/api/filters')
        .then(res => res.json())
        .then(data => {
            fillSelectOptions(document.getElementById('filter-state'), data.states);
            fillSelectOptions(document.getElementById('filter-district'), data.districts);
        })
        .catch(err => console.error('Filter options load failed:', err));
}

// Reload the District list for the selected state ('' = all districts)
function loadDistricts(state) {
    fetch('/api/filters?state=' + encodeURIComponent(state || ''))
        .then(res => res.json())
        .then(data => {
            const distSelect = document.getElementById('filter-district');
            fillSelectOptions(distSelect, data.districts);
            distSelect.value = '';
        })
        .catch(err => console.error('District options load failed:', err));
}

function fetchProjects(page = 1) {
    currentPage = page;
    const search = document.getElementById('filter-search').value.trim();
    const state = document.getElementById('filter-state').value;
    const district = document.getElementById('filter-district').value;
    const risk = document.getElementById('filter-risk').value;
    const status = document.getElementById('filter-status').value;

    const queryParams = new URLSearchParams();
    if (search) queryParams.append('search', search);
    if (state) queryParams.append('state', state);
    if (district) queryParams.append('district', district);
    if (risk) queryParams.append('risk_level', risk);
    if (status) queryParams.append('status', status);
    queryParams.append('page', currentPage);
    queryParams.append('limit', currentLimit);

    const tbody = document.getElementById('projects-tbody');
    tbody.innerHTML = `
        <tr>
            <td colspan="11" class="text-center py-4 text-muted">
                <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                Filtering projects...
            </td>
        </tr>
    `;

    fetch(`/api/projects?${queryParams.toString()}`)
        .then(res => res.json())
        .then(data => {
            totalProjects = data.total || 0;
            totalPages = data.total_pages || 1;
            currentPage = data.page || 1;

            document.getElementById('total-count-badge').textContent = totalProjects.toLocaleString();
            updatePaginationUI();
            renderProjectsTable(data.projects);
        })
        .catch(err => {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger py-4">Error loading data: ${err.message}</td></tr>`;
        });
}

function updatePaginationUI() {
    const start = totalProjects === 0 ? 0 : (currentPage - 1) * currentLimit + 1;
    const end = Math.min(currentPage * currentLimit, totalProjects);
    document.getElementById('pagination-info').textContent = `Showing projects ${start.toLocaleString()} – ${end.toLocaleString()} of ${totalProjects.toLocaleString()}`;
    document.getElementById('page-num-display').textContent = `Page ${currentPage} / ${totalPages}`;

    document.getElementById('btn-prev-page').disabled = (currentPage <= 1);
    document.getElementById('btn-next-page').disabled = (currentPage >= totalPages);
}

function renderProjectsTable(projects) {
    const tbody = document.getElementById('projects-tbody');
    if (!projects || projects.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted py-4">No matching road projects found.</td></tr>`;
        return;
    }

    tbody.innerHTML = projects.map(p => {
        // Roles without AI access receive no risk_level (the Risk column is hidden for them)
        const riskBadge = p.risk_level === undefined ? '' :
                          p.risk_level === 'HIGH' ? '<span class="badge-risk-high">🔴 HIGH</span>' :
                          p.risk_level === 'MEDIUM' ? '<span class="badge-risk-med">🟡 MED</span>' :
                          '<span class="badge-risk-low">🟢 LOW</span>';

        const statusBadge = p.status === 'Completed' ? '<span class="badge bg-success">Completed</span>' :
                            p.status === 'Delayed' ? '<span class="badge bg-danger">Delayed</span>' :
                            '<span class="badge bg-primary">Ongoing</span>';

        return `
            <tr>
                <td class="fw-bold"><span class="badge bg-dark">${p.work_id}</span></td>
                <td class="text-truncate" style="max-width: 250px;" title="${p.description}">
                    ${p.description}
                </td>
                <td><small>${p.state}</small></td>
                <td><small>${p.district}</small></td>
                <td><small class="fw-semibold">${formatINR(p.estimated_cost)}</small></td>
                <td><small class="fw-bold text-dark">${formatINR(p.actual_expenditure)}</small></td>
                <td>
                    <div class="d-flex align-items-center gap-1">
                        <div class="progress flex-grow-1" style="height: 6px; width: 50px;">
                            <div class="progress-bar bg-success" style="width: ${p.physical_progress_pct}%;"></div>
                        </div>
                        <small class="fw-semibold">${p.physical_progress_pct}%</small>
                    </div>
                </td>
                <td>
                    <small class="${p.delay_days > 30 ? 'text-danger fw-bold' : 'text-muted'}">${p.delay_days == null ? 'Unavailable' : p.delay_days+' d'}</small>
                </td>
                <td>${riskBadge}</td>
                <td>${statusBadge}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-primary py-0 px-2" onclick="viewProjectDetails('${p.work_id}')">
                        <i class="bi bi-eye"></i> View
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
