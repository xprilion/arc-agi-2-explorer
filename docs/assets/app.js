/**
 * ARC-AGI Explorer - Client-side JavaScript
 * 
 * Handles:
 * - Dataset filtering and pagination
 * - Submission evaluation
 * - Grid rendering
 */

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Check if two 2D grids are identical.
 */
function gridsEqual(a, b) {
    if (!a || !b) return false;
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
        if (!a[i] || !b[i]) return false;
        if (a[i].length !== b[i].length) return false;
        for (let j = 0; j < a[i].length; j++) {
            if (a[i][j] !== b[i][j]) return false;
        }
    }
    return true;
}

/**
 * Build a diff grid showing matches/mismatches between submitted and expected grids.
 */
function diffGrids(submitted, expected) {
    const maxRows = Math.max(submitted?.length || 0, expected?.length || 0);
    const maxCols = Math.max(
        (submitted && submitted[0]) ? submitted[0].length : 0,
        (expected && expected[0]) ? expected[0].length : 0
    );
    
    const diff = [];
    for (let r = 0; r < maxRows; r++) {
        const row = [];
        for (let c = 0; c < maxCols; c++) {
            const sv = (submitted && r < submitted.length && c < submitted[r].length) 
                ? submitted[r][c] : -1;
            const ev = (expected && r < expected.length && c < expected[r].length) 
                ? expected[r][c] : -1;
            row.push({ value: sv, expected: ev, match: sv === ev });
        }
        diff.push(row);
    }
    return diff;
}

/**
 * Evaluate a submission against solutions.
 */
function evaluateSubmission(submission, solutions, challenges) {
    const results = [];
    let totalCorrect = 0;
    let totalTests = 0;
    
    const puzzleIds = Object.keys(submission).sort();
    
    for (const pid of puzzleIds) {
        if (!challenges[pid]) continue;
        
        const sol = solutions[pid] || [];
        const subEntries = submission[pid]; // array of {attempt_1, attempt_2}
        
        const puzzleResults = [];
        let puzzleCorrect = 0;
        
        for (let testIdx = 0; testIdx < subEntries.length; testIdx++) {
            totalTests++;
            const expected = testIdx < sol.length ? sol[testIdx] : null;
            
            const attempt1 = subEntries[testIdx].attempt_1 || [];
            const attempt2 = subEntries[testIdx].attempt_2 || [];
            
            const a1Match = expected ? gridsEqual(attempt1, expected) : false;
            const a2Match = expected ? gridsEqual(attempt2, expected) : false;
            const correct = a1Match || a2Match;
            
            if (correct) {
                puzzleCorrect++;
                totalCorrect++;
            }
            
            const entry = {
                testIndex: testIdx + 1,
                correct,
                a1Match,
                a2Match,
                attempt1,
                attempt2,
                expected,
                hasSolution: expected !== null,
            };
            
            // Build diff grids for visualization
            if (expected) {
                entry.a1Diff = diffGrids(attempt1, expected);
                entry.a2Diff = diffGrids(attempt2, expected);
            }
            
            puzzleResults.push(entry);
        }
        
        const allCorrect = puzzleCorrect === subEntries.length && subEntries.length > 0;
        
        results.push({
            puzzleId: pid,
            tests: puzzleResults,
            numCorrect: puzzleCorrect,
            numTests: subEntries.length,
            allCorrect,
        });
    }
    
    return {
        results,
        totalCorrect,
        totalTests,
        totalPuzzles: results.length,
        score: totalTests > 0 ? totalCorrect / totalTests : 0,
    };
}

// ============================================================================
// Grid Rendering
// ============================================================================

/**
 * Render a 2D grid as HTML.
 */
function renderGrid(grid, options = {}) {
    if (!grid || !grid.length) return '<div class="arc-grid"></div>';
    
    const rows = grid.length;
    const cols = grid[0]?.length || 0;
    
    let sizeClass = '';
    if (rows > 20 || cols > 20) sizeClass = 'tiny';
    else if (rows > 14 || cols > 14) sizeClass = 'small';
    
    let html = `<div class="arc-grid ${sizeClass}">`;
    for (const row of grid) {
        html += '<div class="arc-grid-row">';
        for (const cell of row) {
            const colorClass = cell >= 0 && cell <= 9 ? `c${cell}` : 'c0';
            html += `<div class="arc-cell ${colorClass}"></div>`;
        }
        html += '</div>';
    }
    html += '</div>';
    return html;
}

/**
 * Render a diff grid with mismatch highlighting.
 */
function renderDiffGrid(diff) {
    if (!diff || !diff.length) return '<div class="arc-grid"></div>';
    
    const rows = diff.length;
    const cols = diff[0]?.length || 0;
    
    let sizeClass = '';
    if (rows > 20 || cols > 20) sizeClass = 'tiny';
    else if (rows > 14 || cols > 14) sizeClass = 'small';
    
    let html = `<div class="arc-grid ${sizeClass}">`;
    for (const row of diff) {
        html += '<div class="arc-grid-row">';
        for (const cell of row) {
            const colorClass = cell.value >= 0 && cell.value <= 9 ? `c${cell.value}` : 'c0';
            const style = cell.match ? '' : 'outline: 2px solid var(--arc-2); outline-offset: -2px; opacity: 0.8;';
            html += `<div class="arc-cell ${colorClass}" style="${style}"></div>`;
        }
        html += '</div>';
    }
    html += '</div>';
    return html;
}

// ============================================================================
// Dataset Filtering (for dataset listing pages)
// ============================================================================

let puzzleIndex = null;
let currentDataset = null;
let currentFilters = { q: '', minSize: null, maxSize: null, minExamples: null, sort: 'id' };
let currentPage = 1;
const perPage = 50;

/**
 * Load the puzzle index JSON.
 */
async function loadPuzzleIndex() {
    if (puzzleIndex) return puzzleIndex;
    
    try {
        const response = await fetch('/data/puzzle-index.json');
        puzzleIndex = await response.json();
        return puzzleIndex;
    } catch (error) {
        console.error('Failed to load puzzle index:', error);
        return null;
    }
}

/**
 * Filter and sort puzzles based on current filters.
 */
function filterPuzzles(puzzles) {
    let filtered = [...puzzles];
    
    // Search by ID
    if (currentFilters.q) {
        const q = currentFilters.q.toLowerCase();
        filtered = filtered.filter(p => p.id.toLowerCase().includes(q));
    }
    
    // Min grid size
    if (currentFilters.minSize !== null) {
        filtered = filtered.filter(p => p.max_rows >= currentFilters.minSize || p.max_cols >= currentFilters.minSize);
    }
    
    // Max grid size
    if (currentFilters.maxSize !== null) {
        filtered = filtered.filter(p => p.max_rows <= currentFilters.maxSize && p.max_cols <= currentFilters.maxSize);
    }
    
    // Min train examples
    if (currentFilters.minExamples !== null) {
        filtered = filtered.filter(p => p.num_train >= currentFilters.minExamples);
    }
    
    // Sort
    const sortFns = {
        'id': (a, b) => a.id.localeCompare(b.id),
        'train': (a, b) => b.num_train - a.num_train,
        'test': (a, b) => b.num_test - a.num_test,
        'size': (a, b) => (b.max_rows * b.max_cols) - (a.max_rows * a.max_cols),
        'colors': (a, b) => b.num_colors - a.num_colors,
    };
    filtered.sort(sortFns[currentFilters.sort] || sortFns['id']);
    
    return filtered;
}

/**
 * Render the puzzle table for dataset pages.
 */
function renderPuzzleTable(puzzles, datasetName) {
    const totalPages = Math.max(1, Math.ceil(puzzles.length / perPage));
    currentPage = Math.min(currentPage, totalPages);
    const start = (currentPage - 1) * perPage;
    const pagePuzzles = puzzles.slice(start, start + perPage);
    
    // Update total count
    const totalEl = document.getElementById('puzzle-total');
    if (totalEl) totalEl.textContent = puzzles.length;
    
    // Render table body
    const tbody = document.getElementById('puzzle-tbody');
    if (!tbody) return;
    
    if (pagePuzzles.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">
                    No puzzles match your filters. Try broadening your search.
                </td>
            </tr>
        `;
    } else {
        tbody.innerHTML = pagePuzzles.map(p => `
            <tr>
                <td>
                    <a href="/puzzle/${datasetName}/${p.id}/" class="mono">${p.id}</a>
                </td>
                <td>${p.num_train}</td>
                <td>${p.num_test}</td>
                <td>${p.max_rows}&times;${p.max_cols}</td>
                <td>
                    <div class="color-legend">
                        ${p.colors.map(c => `<div class="color-swatch" style="background: var(--arc-${c});">${c}</div>`).join('')}
                    </div>
                </td>
                <td>
                    ${p.has_solution 
                        ? '<span style="color: var(--green);">Yes</span>' 
                        : '<span style="color: var(--text-muted);">No</span>'}
                </td>
            </tr>
        `).join('');
    }
    
    // Render pagination
    renderPagination(puzzles.length, totalPages, datasetName);
}

/**
 * Render pagination controls.
 */
function renderPagination(total, totalPages, datasetName) {
    const container = document.getElementById('pagination');
    if (!container) return;
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '';
    
    if (currentPage > 1) {
        html += `<button class="btn btn-secondary" onclick="goToPage(1)">First</button>`;
        html += `<button class="btn btn-secondary" onclick="goToPage(${currentPage - 1})">Prev</button>`;
    }
    
    html += `<span class="page-info">Page ${currentPage} of ${totalPages} (${total} puzzles)</span>`;
    
    if (currentPage < totalPages) {
        html += `<button class="btn btn-secondary" onclick="goToPage(${currentPage + 1})">Next</button>`;
        html += `<button class="btn btn-secondary" onclick="goToPage(${totalPages})">Last</button>`;
    }
    
    container.innerHTML = html;
}

/**
 * Navigate to a specific page.
 */
function goToPage(page) {
    currentPage = page;
    applyFilters();
}

/**
 * Apply current filters and re-render the table.
 */
function applyFilters() {
    if (!puzzleIndex || !currentDataset) return;
    
    const data = puzzleIndex[currentDataset];
    if (!data) return;
    
    const filtered = filterPuzzles(data.puzzles);
    renderPuzzleTable(filtered, currentDataset);
    
    // Update sort link active states
    document.querySelectorAll('[data-sort]').forEach(el => {
        el.classList.toggle('active-sort', el.dataset.sort === currentFilters.sort);
    });
}

/**
 * Initialize dataset page filtering.
 */
async function initDatasetPage(datasetName) {
    currentDataset = datasetName;
    
    // Load index
    await loadPuzzleIndex();
    if (!puzzleIndex) return;
    
    // Set up filter form
    const form = document.getElementById('filter-form');
    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const qInput = document.getElementById('q');
            const minSizeInput = document.getElementById('min_size');
            const maxSizeInput = document.getElementById('max_size');
            const minExamplesInput = document.getElementById('min_examples');
            
            currentFilters.q = qInput?.value || '';
            currentFilters.minSize = minSizeInput?.value ? parseInt(minSizeInput.value) : null;
            currentFilters.maxSize = maxSizeInput?.value ? parseInt(maxSizeInput.value) : null;
            currentFilters.minExamples = minExamplesInput?.value ? parseInt(minExamplesInput.value) : null;
            
            currentPage = 1;
            applyFilters();
        });
    }
    
    // Set up sort links
    document.querySelectorAll('[data-sort]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            currentFilters.sort = el.dataset.sort;
            currentPage = 1;
            applyFilters();
        });
    });
    
    // Set up clear button
    const clearBtn = document.getElementById('clear-filters');
    if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
            e.preventDefault();
            currentFilters = { q: '', minSize: null, maxSize: null, minExamples: null, sort: 'id' };
            currentPage = 1;
            
            // Clear form inputs
            const qInput = document.getElementById('q');
            const minSizeInput = document.getElementById('min_size');
            const maxSizeInput = document.getElementById('max_size');
            const minExamplesInput = document.getElementById('min_examples');
            if (qInput) qInput.value = '';
            if (minSizeInput) minSizeInput.value = '';
            if (maxSizeInput) maxSizeInput.value = '';
            if (minExamplesInput) minExamplesInput.value = '';
            
            applyFilters();
        });
    }
    
    // Initial render
    applyFilters();
}

// ============================================================================
// Submission Evaluation (for submissions page)
// ============================================================================

let solutionsData = {};
let challengesData = {};
let currentEvaluation = null;
let currentSubmissionName = '';

/**
 * Load solutions for a specific dataset.
 */
async function loadSolutions(datasetName) {
    const solutionFiles = {
        'training': 'arc-agi_training_solutions.json',
        'evaluation': 'arc-agi_evaluation_solutions.json',
        'test': 'arc-agi_training_solutions.json', // test uses training solutions
    };
    
    const challengeFiles = {
        'training': 'arc-agi_training_challenges.json',
        'evaluation': 'arc-agi_evaluation_challenges.json',
        'test': 'arc-agi_test_challenges.json',
    };
    
    try {
        const [solResponse, chalResponse] = await Promise.all([
            fetch(`/data/${solutionFiles[datasetName]}`),
            fetch(`/data/${challengeFiles[datasetName]}`),
        ]);
        
        solutionsData = await solResponse.json();
        challengesData = await chalResponse.json();
        
        return true;
    } catch (error) {
        console.error('Failed to load solutions:', error);
        return false;
    }
}

/**
 * Handle file upload and evaluation.
 */
async function handleSubmissionUpload(file, datasetName) {
    // Show loading state
    const resultsContainer = document.getElementById('evaluation-results');
    if (resultsContainer) {
        resultsContainer.innerHTML = '<p style="color: var(--text-muted);">Loading...</p>';
    }
    
    // Load solutions
    const loaded = await loadSolutions(datasetName);
    if (!loaded) {
        if (resultsContainer) {
            resultsContainer.innerHTML = '<p style="color: var(--arc-2);">Failed to load solution data.</p>';
        }
        return;
    }
    
    // Read the submission file
    try {
        const text = await file.text();
        const submission = JSON.parse(text);
        currentSubmissionName = file.name;
        
        // Evaluate
        currentEvaluation = evaluateSubmission(submission, solutionsData, challengesData);
        
        // Render results
        renderEvaluationResults(currentEvaluation, datasetName);
        
        // Update current file display
        const fileDisplay = document.getElementById('current-file');
        if (fileDisplay) {
            fileDisplay.innerHTML = `Current file: <strong style="color: var(--text);">${currentSubmissionName}</strong>`;
        }
        
    } catch (error) {
        console.error('Failed to parse submission:', error);
        if (resultsContainer) {
            resultsContainer.innerHTML = '<div class="card" style="border-color: var(--arc-2);"><p style="color: var(--arc-2);">Invalid JSON file. Please upload a valid submission JSON.</p></div>';
        }
    }
}

/**
 * Render evaluation results summary and table.
 */
function renderEvaluationResults(evaluation, datasetName) {
    const container = document.getElementById('evaluation-results');
    if (!container) return;
    
    const scorePercent = (evaluation.score * 100).toFixed(1);
    
    let html = `
        <!-- Score summary -->
        <div class="card">
            <h2 style="margin-bottom: 12px;">Results</h2>
            <div class="stats">
                <div class="stat">
                    <div class="value" style="color: var(--green);">${scorePercent}%</div>
                    <div class="label">Score</div>
                </div>
                <div class="stat">
                    <div class="value">${evaluation.totalCorrect}</div>
                    <div class="label">Correct Tests</div>
                </div>
                <div class="stat">
                    <div class="value">${evaluation.totalTests}</div>
                    <div class="label">Total Tests</div>
                </div>
                <div class="stat">
                    <div class="value">${evaluation.totalPuzzles}</div>
                    <div class="label">Puzzles Evaluated</div>
                </div>
            </div>
        </div>
        
        <!-- Results table -->
        <div class="section-header">
            Puzzle Results
            <span class="badge">${evaluation.results.length} puzzles</span>
        </div>
        
        <div class="card" style="padding: 0; overflow-x: auto;">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Puzzle ID</th>
                        <th>Tests</th>
                        <th>Correct</th>
                        <th>Status</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    ${evaluation.results.map((r, idx) => `
                        <tr>
                            <td style="color: var(--text-muted);">${idx + 1}</td>
                            <td><span class="mono">${r.puzzleId}</span></td>
                            <td>${r.numTests}</td>
                            <td>${r.numCorrect} / ${r.numTests}</td>
                            <td>
                                ${r.allCorrect 
                                    ? '<span style="color: var(--green); font-weight: 600;">Pass</span>'
                                    : r.numCorrect > 0
                                        ? '<span style="color: var(--yellow); font-weight: 600;">Partial</span>'
                                        : '<span style="color: var(--arc-2); font-weight: 600;">Fail</span>'
                                }
                            </td>
                            <td>
                                <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="showPuzzleDetail(${idx}, '${datasetName}')">View Diff</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    container.innerHTML = html;
}

/**
 * Show detailed diff view for a puzzle.
 */
function showPuzzleDetail(puzzleIndex, datasetName) {
    if (!currentEvaluation) return;
    
    const detail = currentEvaluation.results[puzzleIndex];
    if (!detail) return;
    
    // Get test inputs from challenges data
    const challenge = challengesData[detail.puzzleId] || {};
    const testInputs = (challenge.test || []).map(t => t.input || []);
    
    const container = document.getElementById('evaluation-results');
    if (!container) return;
    
    // Build navigation
    const prevIndex = puzzleIndex > 0 ? puzzleIndex - 1 : null;
    const nextIndex = puzzleIndex < currentEvaluation.results.length - 1 ? puzzleIndex + 1 : null;
    
    let html = `
        <div class="breadcrumb">
            <a href="#" onclick="backToResults('${datasetName}'); return false;">Results</a>
            <span class="sep">/</span><span class="mono">${detail.puzzleId}</span>
        </div>
        
        <h1>
            <span class="mono">${detail.puzzleId}</span>
            <span class="subtitle">- Submission Diff</span>
        </h1>
        
        <!-- Summary -->
        <div class="card">
            <div class="stats">
                <div class="stat">
                    <div class="value">${detail.numTests}</div>
                    <div class="label">Test Cases</div>
                </div>
                <div class="stat">
                    <div class="value">${detail.numCorrect}</div>
                    <div class="label">Correct</div>
                </div>
                <div class="stat">
                    <div class="value">
                        ${detail.allCorrect 
                            ? '<span style="color: var(--green);">Pass</span>'
                            : detail.numCorrect > 0
                                ? '<span style="color: var(--yellow);">Partial</span>'
                                : '<span style="color: var(--arc-2);">Fail</span>'
                        }
                    </div>
                    <div class="label">Status</div>
                </div>
            </div>
        </div>
    `;
    
    // Render each test
    for (const t of detail.tests) {
        html += `
            <div class="card">
                <div style="font-size: 13px; font-weight: 600; color: var(--text-muted); margin-bottom: 12px; display: flex; align-items: center; gap: 10px;">
                    Test ${t.testIndex}
                    ${t.correct 
                        ? '<span style="background: var(--green); color: #000; font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 700;">CORRECT</span>'
                        : '<span style="background: var(--arc-2); color: #fff; font-size: 11px; padding: 2px 8px; border-radius: 12px; font-weight: 700;">WRONG</span>'
                    }
                </div>
        `;
        
        // Input grid
        if (testInputs[t.testIndex - 1]) {
            html += `
                <div style="margin-bottom: 16px;">
                    <div style="font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Input</div>
                    ${renderGrid(testInputs[t.testIndex - 1])}
                </div>
            `;
        }
        
        html += `<div style="display: flex; gap: 32px; flex-wrap: wrap;">`;
        
        // Expected solution
        if (t.hasSolution) {
            const edims = t.expected ? `${t.expected.length}&times;${t.expected[0]?.length || 0}` : '';
            html += `
                <div class="grid-panel">
                    <div class="grid-label" style="color: var(--green);">Expected Solution</div>
                    ${renderGrid(t.expected)}
                    <div class="grid-meta">${edims}</div>
                </div>
            `;
        }
        
        // Attempt 1
        const a1dims = t.attempt1 ? `${t.attempt1.length}&times;${t.attempt1[0]?.length || 0}` : '';
        html += `
            <div class="grid-panel">
                <div class="grid-label" style="color: ${t.a1Match ? 'var(--green)' : 'var(--arc-2)'};">
                    Attempt 1 ${t.a1Match ? '&#10003;' : '&#10007;'}
                </div>
                ${t.hasSolution && t.a1Diff ? renderDiffGrid(t.a1Diff) : renderGrid(t.attempt1)}
                <div class="grid-meta">${a1dims}</div>
            </div>
        `;
        
        // Attempt 2
        const a2dims = t.attempt2 ? `${t.attempt2.length}&times;${t.attempt2[0]?.length || 0}` : '';
        html += `
            <div class="grid-panel">
                <div class="grid-label" style="color: ${t.a2Match ? 'var(--green)' : 'var(--arc-2)'};">
                    Attempt 2 ${t.a2Match ? '&#10003;' : '&#10007;'}
                </div>
                ${t.hasSolution && t.a2Diff ? renderDiffGrid(t.a2Diff) : renderGrid(t.attempt2)}
                <div class="grid-meta">${a2dims}</div>
            </div>
        `;
        
        html += `</div>`; // close flex container
        
        if (!t.hasSolution) {
            html += `<p style="color: var(--yellow); font-size: 13px; margin-top: 8px;">No ground-truth solution available for comparison.</p>`;
        }
        
        html += `</div>`; // close card
    }
    
    // Navigation
    html += `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border);">
            <div style="display: flex; gap: 8px;">
                ${prevIndex !== null 
                    ? `<button class="btn btn-secondary" onclick="showPuzzleDetail(${prevIndex}, '${datasetName}')">&larr; Previous</button>`
                    : '<span class="btn btn-secondary" style="opacity: 0.4; cursor: default;">&larr; Previous</span>'
                }
                <button class="btn btn-secondary" onclick="backToResults('${datasetName}')">Back to Results</button>
            </div>
            <div>
                ${nextIndex !== null 
                    ? `<button class="btn btn-secondary" onclick="showPuzzleDetail(${nextIndex}, '${datasetName}')">Next &rarr;</button>`
                    : '<span class="btn btn-secondary" style="opacity: 0.4; cursor: default;">Next &rarr;</span>'
                }
            </div>
        </div>
    `;
    
    container.innerHTML = html;
    
    // Scroll to top
    window.scrollTo(0, 0);
}

/**
 * Go back to evaluation results summary.
 */
function backToResults(datasetName) {
    if (currentEvaluation) {
        renderEvaluationResults(currentEvaluation, datasetName);
    }
}

/**
 * Initialize submissions page.
 */
function initSubmissionsPage() {
    const form = document.getElementById('upload-form');
    if (!form) return;
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const fileInput = document.getElementById('file');
        const datasetSelect = document.getElementById('dataset');
        
        if (!fileInput?.files?.[0]) {
            alert('Please select a file to upload.');
            return;
        }
        
        const file = fileInput.files[0];
        const datasetName = datasetSelect?.value || 'evaluation';
        
        await handleSubmissionUpload(file, datasetName);
    });
}

// ============================================================================
// Global initialization
// ============================================================================

// Make functions available globally
window.goToPage = goToPage;
window.showPuzzleDetail = showPuzzleDetail;
window.backToResults = backToResults;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on a dataset page
    const datasetContainer = document.getElementById('dataset-page');
    if (datasetContainer) {
        const datasetName = datasetContainer.dataset.name;
        if (datasetName) {
            initDatasetPage(datasetName);
        }
    }
    
    // Check if we're on submissions page
    const submissionsContainer = document.getElementById('submissions-page');
    if (submissionsContainer) {
        initSubmissionsPage();
    }
});
