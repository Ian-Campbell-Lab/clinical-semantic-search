// HELPERS
function submitform(form) {
    if (!form.checkValidity()) return false;
    const rightCol = document.querySelector('.right-col');
    if (rightCol) {
        rightCol.querySelectorAll('.card:not(#loading-message)')
            .forEach(card => card.style.display = 'none');
    }
    const loadingMsg = document.getElementById("loading-message");
    if (loadingMsg) loadingMsg.style.display = "block";
    form.submit();
    return true;
}


function clearWorkspaceHiddenFields(form) {
    form.querySelectorAll('.workspace-mrn-field').forEach(el => el.remove());
}

function addHiddenField(form, name, value) {
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = name;
    input.value = value;
    input.classList.add('workspace-mrn-field');
    form.appendChild(input);
}


function addHiddenFieldIfValue(form, name, value) {
    if (!value) return;
    if (Array.isArray(value) && value.length === 0) return;
    addHiddenField(
        form,
        name,
        Array.isArray(value) ? value.join(', ') : value
    );
}


function showStartupDisclaimer() {
    // Show only once per browser tab/session
    const alreadyShown = sessionStorage.getItem('startupDisclaimerShown') === 'true';
    if (alreadyShown) return;

    const overlay = document.getElementById('compliance-overlay');
    const acceptBtn = document.getElementById('compliance-accept-btn');

    if (!overlay || !acceptBtn) return;

    // Show modal
    overlay.classList.add('show');
    acceptBtn.focus();

    // Close handlers (accept button, backdrop click, ESC)
    const close = () => {
        overlay.classList.remove('show');
        sessionStorage.setItem('startupDisclaimerShown', 'true');
        // Clean up listeners after closing
        overlay.removeEventListener('click', backdropHandler);
        document.removeEventListener('keydown', escHandler);
    };

    acceptBtn.addEventListener('click', close, { once: true });

    const backdropHandler = (e) => {
        if (e.target === overlay) close();
    };
    overlay.addEventListener('click', backdropHandler);

    const escHandler = (e) => {
        if (e.key === 'Escape') close();
    };
    document.addEventListener('keydown', escHandler);

}


// Store filter options from backend
    const filterStates = {
        note_category: { include: [], exclude: [], selected: null },
        encounter_type: { include: [], exclude: [], selected: null },
        department: { include: [], exclude: [], selected: null },
        specialty: { include: [], exclude: [], selected: null },
        author_type: { include: [], exclude: [], selected: null },
        author_name: { include: [], exclude: [], selected: null }
    };

    const visibleFilters = new Set();
    let selectedIndex = -1;
    let workspaceManageMode = false;

    // Add Filter dropdown functionality
    const addFilterBtn = document.getElementById('add-filter-btn');
    const filterDropdown = document.getElementById('filter-dropdown');

    addFilterBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        filterDropdown.classList.toggle('show');
        updateDropdownItems();
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!filterDropdown.contains(e.target) && e.target !== addFilterBtn) {
            filterDropdown.classList.remove('show');
        }
    });

    // Handle filter selection from dropdown
    filterDropdown.addEventListener('click', function(e) {
        const item = e.target.closest('.filter-dropdown-item');
        if (item && !item.classList.contains('disabled')) {
            const filterName = item.dataset.filter;
            showFilterGroup(filterName);
            filterDropdown.classList.remove('show');
        }
    });

    function updateDropdownItems() {
        const items = filterDropdown.querySelectorAll('.filter-dropdown-item');
        items.forEach(item => {
            const filterName = item.dataset.filter;
            if (visibleFilters.has(filterName)) {
                item.classList.add('disabled');
            } else {
                item.classList.remove('disabled');
            }
        });
    }

    function showFilterGroup(filterName) {
        const filterGroup = document.getElementById(`filter-${filterName}`);
        if (filterGroup) {
            filterGroup.classList.remove('hidden');
            visibleFilters.add(filterName);
            
            const addFilterContainer = document.querySelector('.add-filter-container');
            if (addFilterContainer && addFilterContainer.parentNode) {
                addFilterContainer.parentNode.appendChild(filterGroup);
            }
            
            updateDropdownItems();
            
            setTimeout(() => {
                filterGroup.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
        }
    }

    function removeFilterGroup(filterName) {
        const filterGroup = document.getElementById(`filter-${filterName}`);
        if (filterGroup) {
            filterGroup.classList.add('hidden');
            visibleFilters.delete(filterName);
            
            if (filterStates[filterName]) {
                filterStates[filterName].include = [];
                filterStates[filterName].exclude = [];
                filterStates[filterName].selected = null;
                updateTags(filterName);
            }
            
            const inputs = filterGroup.querySelectorAll('input');
            inputs.forEach(input => input.value = '');
            
            updateHiddenInputs();
            updateDropdownItems();
        }
    }

    // Setup autocomplete for each filter
    Object.keys(filterOptions).forEach(filterName => {
        const input = document.getElementById(`${filterName}-input`);
        const dropdown = document.getElementById(`${filterName}-dropdown`);

        if (!input || !dropdown) return;

        function showDropdown(query) {
            query = query.toLowerCase();
            
            const matches = filterOptions[filterName].filter(opt => 
                opt.text.toLowerCase().includes(query)
            );

            if (matches.length === 0) {
                dropdown.classList.remove('show');
                input.classList.remove('dropdown-open');
                dropdown.innerHTML = '';
                return;
            }

            dropdown.innerHTML = matches.map((opt, idx) => 
                `<div class="autocomplete-item" data-value="${opt.id}" data-text="${opt.text}" data-index="${idx}">${opt.text}</div>`
            ).join('');
            
            dropdown.classList.add('show');
            input.classList.add('dropdown-open');
            selectedIndex = -1;

            dropdown.querySelectorAll('.autocomplete-item').forEach(item => {
                item.addEventListener('click', function() {
                    filterStates[filterName].selected = {
                        value: this.dataset.value,
                        text: this.dataset.text
                    };
                    input.value = this.dataset.text;
                    dropdown.classList.remove('show');
                    input.classList.remove('dropdown-open');
                });
            });
        }

        input.addEventListener('focus', function() {
            const query = this.value.trim();
            showDropdown(query);
        });

        input.addEventListener('click', function() {
            const query = this.value.trim();
            showDropdown(query);
        });

        input.addEventListener('input', function() {
            const query = this.value.trim();
            showDropdown(query);
        });

        input.addEventListener('keydown', function(e) {
            const items = dropdown.querySelectorAll('.autocomplete-item');
            
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                updateSelection(items);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, -1);
                updateSelection(items);
            } else if (e.key === 'Enter' && selectedIndex >= 0) {
                e.preventDefault();
                items[selectedIndex].click();
            } else if (e.key === 'Escape') {
                dropdown.classList.remove('show');
                input.classList.remove('dropdown-open');
            }
        });

        input.addEventListener('blur', function() {
            setTimeout(() => {
                dropdown.classList.remove('show');
                input.classList.remove('dropdown-open');
            }, 200);
        });
    });

    function updateSelection(items) {
        items.forEach((item, idx) => {
            item.classList.toggle('selected', idx === selectedIndex);
        });
        if (selectedIndex >= 0) {
            items[selectedIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    function addFilter(filterName, mode) {
        const selected = filterStates[filterName].selected;
        
        if (!selected) {
            return;
        }

        const oppositeMode = mode === 'include' ? 'exclude' : 'include';
        
        if (filterStates[filterName][oppositeMode].some(item => item.value === selected.value)) {
            return;
        }

        if (filterStates[filterName][mode].some(item => item.value === selected.value)) {
            return;
        }

        filterStates[filterName][mode].push(selected);
        filterStates[filterName].selected = null;
        
        document.getElementById(`${filterName}-input`).value = '';
        updateTags(filterName);
        updateHiddenInputs();
    }

    function updateTags(filterName) {
        const container = document.getElementById(`${filterName}-tags`);
        if (!container) return;
        
        container.innerHTML = '';

        ['include', 'exclude'].forEach(mode => {
            filterStates[filterName][mode].forEach((item, index) => {
                const tag = document.createElement('span');
                tag.className = `filter-tag ${mode}`;
                tag.innerHTML = `${item.text}<span class="tag-remove" onclick="removeTag('${filterName}', '${mode}', ${index})">&times;</span>`;
                container.appendChild(tag);
            });
        });
    }

    function removeTag(filterName, mode, index) {
        filterStates[filterName][mode].splice(index, 1);
        updateTags(filterName);
        updateHiddenInputs();
    }

    function updateHiddenInputs() {
        const container = document.getElementById('hidden-filters');
        container.innerHTML = '';

        Object.keys(filterStates).forEach(filterName => {
            filterStates[filterName].include.forEach(item => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = `${filterName}_include`;
                input.value = item.value;
                container.appendChild(input);
            });

            filterStates[filterName].exclude.forEach(item => {
                const input = document.createElement('input');
                input.type = 'hidden';
                input.name = `${filterName}_exclude`;
                input.value = item.value;
                container.appendChild(input);
            });
        });
    }

    function applySuggestedFilters(filterName) {
        const suggestedFilters = {
            note_category: [
                "Consult Note",
                "Discharge Summary",
                "H&P",
                "OP Note - Brief (Needs Dictation)",
                "OP Note - Complete (Template or Full Dictation)",
                "Procedures",
                "Progress Note",
                "Progress Notes"
            ],
            encounter_type: [
                "Hospital Encounter",
                "Office Visit"
            ],
            author_type: [
                'Physician',
                'Nurse Practitioner',
                'Resident',
                'Audiologist',
                'Anesthesiologist',
                'Psychologist',
                'Physician Assistant',
                'FELLOW',
                'Genetic Counselor',
                'Midwife',
                'Neuropsychologist',
                'Psychology Intern',
                'Psychology Postdoctoral Fellow',
                'FELLOW-CRNA',
                'APP Fellow'
            ]
        };

        const suggested = suggestedFilters[filterName];
        if (!suggested) return;

        suggested.forEach(text => {
            const option = filterOptions[filterName].find(opt => opt.text === text);
            if (option) {
                const alreadyIncluded = filterStates[filterName].include.some(item => item.value === option.id);
                const inExclude = filterStates[filterName].exclude.some(item => item.value === option.id);
                
                if (!alreadyIncluded && !inExclude) {
                    filterStates[filterName].include.push({
                        value: option.id,
                        text: option.text
                    });
                }
            }
        });

        updateTags(filterName);
        updateHiddenInputs();
    }

    // Clear Filters should NOT clear workspace data
    document.getElementById("refresh-btn").addEventListener("click", function() {
        
        document.querySelector("form").reset();
        
        // Reset checkboxes to defaults
        document.getElementById('query-prefix-checkbox').checked = true;
        document.getElementById('save-results-checkbox').checked = false;
        
        visibleFilters.forEach(filterName => {
            removeFilterGroup(filterName);
        });
        visibleFilters.clear();
        
        Object.keys(filterStates).forEach(filterName => {
            filterStates[filterName].include = [];
            filterStates[filterName].exclude = [];
            filterStates[filterName].selected = null;
            updateTags(filterName);
        });
        updateHiddenInputs();
        
        document.querySelectorAll('input, textarea').forEach(el => {
            if (el.type !== 'checkbox') {
                el.value = '';
            }
        });
        
        document.querySelector('input[name="n_notes"]').value = '3';
        
        // Reset question textarea height
        const questionTextarea = document.getElementById('question-textarea');
        if (questionTextarea) {
            questionTextarea.style.height = 'auto';
            localStorage.removeItem('questionTextareaHeight');
        }
        
        // Reset MRN include textarea height
        const mrnsTextarea = document.getElementById('mrns-textarea');
        if (mrnsTextarea) {
            mrnsTextarea.style.height = 'auto';
            localStorage.removeItem('mrnsTextareaHeight');
        }
        
        // Reset MRN exclude textarea height
        const mrnsExcludeTextarea = document.getElementById('mrns-exclude-textarea');
        if (mrnsExcludeTextarea) {
            mrnsExcludeTextarea.style.height = 'auto';
            localStorage.removeItem('mrnsExcludeTextareaHeight');
        }
        
        const rightCol = document.querySelector('.right-col');
        if (rightCol) {
            rightCol.innerHTML = `
                <div class="card" style="text-align: center; padding: 40px; color: #666;">
                    <h3 style="color: #999;">Notes will appear here</h3>
                    <p>Enter a question and click "Search" to retrieve relevant notes.</p>
                </div>
            `;
        }
        
        const loadingMsg = document.getElementById("loading-message");
        if (loadingMsg) {
            loadingMsg.style.display = "none";
        }
        
        updateDropdownItems();
    });

    function restoreFiltersFromURL() {
        const urlParams = new URLSearchParams(window.location.search);
        
        Object.keys(filterStates).forEach(filterName => {
            let hasFilters = false;
            
            urlParams.getAll(`${filterName}_include`).forEach(value => {
                const option = filterOptions[filterName].find(opt => opt.id === value);
                if (option) {
                    filterStates[filterName].include.push({ value: option.id, text: option.text });
                    hasFilters = true;
                }
            });
            
            urlParams.getAll(`${filterName}_exclude`).forEach(value => {
                const option = filterOptions[filterName].find(opt => opt.id === value);
                if (option) {
                    filterStates[filterName].exclude.push({ value: option.id, text: option.text });
                    hasFilters = true;
                }
            });
            
            if (hasFilters) {
                showFilterGroup(filterName);
            }
            
            updateTags(filterName);
        });
        
        if (urlParams.get('crowding_neighbor_count')) {
            showFilterGroup('notes_per_patient');
        }
        if (urlParams.get('start_date') || urlParams.get('end_date')) {
            showFilterGroup('date_range');
        }
        
        updateHiddenInputs();
    }

    document.getElementById("ask-btn").addEventListener("click", (e) => {
        const form = document.querySelector("form");
        if (form.checkValidity()) {
            const rightCol = document.querySelector('.right-col');
            if (rightCol) {
                rightCol.querySelectorAll('.card:not(#loading-message)').forEach(card => {
                    card.style.display = 'none';
                });
            }
            const loadingMsg = document.getElementById("loading-message");
            if (loadingMsg) {
                loadingMsg.style.display = "block";
            }
        }
    });

    document.getElementById("ask-btn").addEventListener("click", function () {
    workspaceManageMode = false;
    updateMRNButtonStates();
});

    // Search More button (top) - excludes returned MRNs AND all workspace MRNs
    document.getElementById("search-more-btn").addEventListener("click", function() {
        // Collect MRNs from search results
        const displayMRNs = Array.from(document.querySelectorAll('#MRN-buttons button'))
            .map(btn => btn.textContent.replace('MRN ', '').trim())
            .filter(m => m);
        
        // Collect MRNs from workspace (both include and exclude lists)
        const workspaceMRNs = [...cohortWorkspace.includeMRNs, ...cohortWorkspace.excludeMRNs];
        
        // Combine all MRNs to exclude (remove duplicates)
        const allExcludeMRNs = [...new Set([...displayMRNs, ...workspaceMRNs])];
        
        if (allExcludeMRNs.length === 0) {
            showStatusToast('No MRNs to exclude.', 'error');
            return;
        }

        const form = document.querySelector("form");

        // Remove any existing hidden fields from prior runs
        clearWorkspaceHiddenFields(form);


        // Get include MRNs from text area
        const mrnsTextarea = document.getElementById('mrns-textarea');
        const manualInclude = mrnsTextarea.value.trim();
        const manualIncludeMRNs = manualInclude? manualInclude.split(/[,\s]+/).map(m => m.trim()).filter(m => m): [];
        if (mrnsTextarea) mrnsTextarea.value = '';
      
        // Get manually entered exclude MRNs and combine them
        const mrnsExcludeTextarea = document.getElementById('mrns-exclude-textarea');
        const manualExclude = mrnsExcludeTextarea.value.trim();
        const manualMRNs = manualExclude ? manualExclude.split(/[,\s]+/).map(m => m.trim()).filter(m => m) : [];
        
        // Combine with manual excludes
        const finalExcludeMRNs = [...new Set([...allExcludeMRNs, ...manualMRNs, ...manualIncludeMRNs])];

        // Instead of writing to the textarea, create a hidden input
        addHiddenFieldIfValue(form, 'mrns_exclude', finalExcludeMRNs);
 
        // Submit
        submitform(document.querySelector("form"));
    });

    // Resizer with localStorage persistence (left/right columns)
    const resizer = document.querySelector('.resizer');
    const leftCol = document.querySelector('.left-col');
    const container = document.querySelector('.layout');
    let isResizing = false;

    const savedWidth = localStorage.getItem('leftColWidth');
    if (savedWidth) {
        leftCol.style.flex = `0 0 ${savedWidth}px`;
    }

    if (resizer) {
        resizer.addEventListener('mousedown', () => { isResizing = true; });
        document.addEventListener('mousemove', e => {
            if (!isResizing) return;
            let newWidth = e.clientX - container.offsetLeft;
            if (newWidth > 150) {
                leftCol.style.flex = `0 0 ${newWidth}px`;
                localStorage.setItem('leftColWidth', newWidth);
            }
        });
        document.addEventListener('mouseup', () => { isResizing = false; });
    }

    // Left column resizer (between question and filters)
    function setupLeftColResizer() {
        const leftColResizer = document.getElementById('left-col-resizer');
        const questionCard = document.querySelector('.question-card');
        const filtersCard = document.getElementById('filters-card');
        let isResizingLeftCol = false;
        
        if (leftColResizer && questionCard && filtersCard) {
            leftColResizer.addEventListener('mousedown', (e) => { 
                isResizingLeftCol = true;
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', e => {
                if (!isResizingLeftCol) return;
                e.preventDefault();
                
                const leftColRect = leftCol.getBoundingClientRect();
                const relativeY = e.clientY - leftColRect.top;
                const newHeight = relativeY;
                
                if (newHeight > 80 && newHeight < leftColRect.height - 200) {
                    questionCard.style.height = newHeight + 'px';
                    questionCard.style.flex = 'none';
                    filtersCard.style.flex = '1 1 auto';
                    localStorage.setItem('questionCardHeight', newHeight);
                }
            });
            
            document.addEventListener('mouseup', () => { 
                isResizingLeftCol = false; 
            });
        }
    }
    
    setupLeftColResizer();

    // MRN buttons resizer
    function setupMRNResizer() {
        const mrnResizer = document.getElementById('mrn-resizer');
        const mrnButtons = document.getElementById('MRN-buttons');
        let isResizingMRN = false;
        
        if (mrnResizer && mrnButtons) {
            const savedMRNHeight = localStorage.getItem('mrnButtonsHeight');
            if (savedMRNHeight) {
                mrnButtons.style.maxHeight = savedMRNHeight + 'px';
            }
            
            mrnResizer.addEventListener('mousedown', (e) => { 
                isResizingMRN = true;
                e.preventDefault();
            });
            
            document.addEventListener('mousemove', e => {
                if (!isResizingMRN) return;
                e.preventDefault();
                
                const rect = mrnButtons.getBoundingClientRect();
                const newHeight = e.clientY - rect.top;
                if (newHeight > 30 && newHeight < 400) {
                    mrnButtons.style.maxHeight = newHeight + 'px';
                    localStorage.setItem('mrnButtonsHeight', newHeight);
                }
            });
            
            document.addEventListener('mouseup', () => { 
                isResizingMRN = false; 
            });
        }
    }
    
    if (document.getElementById('mrn-resizer')) {
        setupMRNResizer();
    }

    // Note buttons resizers
    function setupNoteResizers() {
        document.querySelectorAll('.note-resizer').forEach(resizer => {
            const mrn = resizer.dataset.mrn;
            const noteButtons = document.getElementById(`note-buttons-${mrn}`);
            let isResizingNote = false;
            
            if (noteButtons) {
                const savedNoteHeight = localStorage.getItem(`noteButtons-${mrn}-height`);
                if (savedNoteHeight) {
                    noteButtons.style.maxHeight = savedNoteHeight + 'px';
                }
                
                resizer.addEventListener('mousedown', (e) => { 
                    isResizingNote = true;
                    e.preventDefault();
                });
                
                document.addEventListener('mousemove', e => {
                    if (!isResizingNote) return;
                    e.preventDefault();
                    
                    const rect = noteButtons.getBoundingClientRect();
                    const newHeight = e.clientY - rect.top;
                    if (newHeight > 30 && newHeight < 400) {
                        noteButtons.style.maxHeight = newHeight + 'px';
                        localStorage.setItem(`noteButtons-${mrn}-height`, newHeight);
                    }
                });
                
                document.addEventListener('mouseup', () => { 
                    isResizingNote = false; 
                });
            }
        });
    }
    
    if (document.querySelectorAll('.note-resizer').length > 0) {
        setupNoteResizers();
    }

    // Date validation
    const startDateInput = document.getElementById("start_date");
    const endDateInput = document.getElementById("end_date");

    if (startDateInput && endDateInput) {
        startDateInput.addEventListener("change", function() {
            if (this.value) {
                endDateInput.min = this.value;
                if (endDateInput.value && endDateInput.value < this.value) {
                    endDateInput.value = "";
                }
            }
        });

        endDateInput.addEventListener("change", function() {
            if (startDateInput.value && this.value && this.value < startDateInput.value) {
                this.value = "";
            }
        });
    }

    // ============================================
    // COHORT WORKSPACE
    // ============================================

    let cohortWorkspace = {
        includeMRNs: [],
        excludeMRNs: []
    };

    // Save workspace to sessionStorage only
    function saveWorkspace() {
        try {
            updateWorkspaceSession();
        } catch (e) {
            console.error('Error saving workspace to session:', e);
        }
    }

    // Update MRN button visual states
    function updateMRNButtonStates() {
        const mrnButtons = document.querySelectorAll('#MRN-buttons button');
        mrnButtons.forEach(btn => {
            const mrn = btn.textContent.replace('MRN ', '').trim();
            
            // Remove all workspace classes
            btn.classList.remove('workspace-included', 'workspace-excluded');
            
            if (!workspaceManageMode) {
                // Manage mode OFF: don't show any visual indicators
                return;
            }
            
            // Manage mode ON: Show actual state or default to included
            if (cohortWorkspace.excludeMRNs.includes(mrn)) {
                btn.classList.add('workspace-excluded');
            } else if (cohortWorkspace.includeMRNs.includes(mrn)) {
                btn.classList.add('workspace-included');
            } else {
                // Default state in manage mode: show as included (green checkmark)
                btn.classList.add('workspace-included');
            }
        });
    }

    // Show status toast notification
    function showStatusToast(message, type = 'success') {
        let toast = document.querySelector('.status-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'status-toast';
            document.body.appendChild(toast);
        }
        
        toast.textContent = message;
        toast.className = `status-toast ${type} show`;
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 2000);
    }

    // Toggle workspace panel with auto-expand on first add
    function toggleWorkspace() {
        const content = document.getElementById('workspace-content');
        const toggle = document.getElementById('workspace-toggle');
        const actions = document.getElementById('workspace-actions');
        
        content.classList.toggle('collapsed');
        toggle.classList.toggle('collapsed');
        
        // Show/hide action buttons based on workspace state
        if (content.classList.contains('collapsed')) {
            actions.classList.remove('show');
            sessionStorage.setItem('workspaceCollapsed', 'true');
        } else {
            actions.classList.add('show');
            sessionStorage.setItem('workspaceCollapsed', 'false');
        }
    }

    // Auto-expand workspace when adding MRNs
    function ensureWorkspaceExpanded() {
        const content = document.getElementById('workspace-content');
        const toggle = document.getElementById('workspace-toggle');
        const actions = document.getElementById('workspace-actions');
        
        if (content.classList.contains('collapsed')) {
            content.classList.remove('collapsed');
            toggle.classList.remove('collapsed');
            actions.classList.add('show');
            sessionStorage.setItem('workspaceCollapsed', 'false');
        }
    }

    // Add all current MRNs to workspace include list (moves from exclude if needed)
    function addAllToWorkspace() {
        const mrnButtons = document.querySelectorAll('#MRN-buttons button');
        const currentMRNs = Array.from(mrnButtons).map(btn => {
            return btn.textContent.replace('MRN ', '').trim();
        });
        
        if (currentMRNs.length === 0) {
            return;
        }
        
        let addedCount = 0;
        let movedCount = 0;
        
        currentMRNs.forEach(mrn => {
            // Remove from exclude if present
            const excludeIndex = cohortWorkspace.excludeMRNs.indexOf(mrn);
            if (excludeIndex > -1) {
                cohortWorkspace.excludeMRNs.splice(excludeIndex, 1);
                movedCount++;
            }
            
            // Add to include if not already there
            if (!cohortWorkspace.includeMRNs.includes(mrn)) {
                cohortWorkspace.includeMRNs.push(mrn);
                addedCount++;
            }
        });
        
        saveWorkspace();
        displayWorkspace();
        updateMRNButtonStates();
        
        // Expand workspace when adding MRNs
        ensureWorkspaceExpanded();
    
    }

    // Copy all returned MRNs to clipboard
    function copyAllMRNs() {
        const mrnButtons = document.querySelectorAll('#MRN-buttons button');
        const mrnList = Array.from(mrnButtons).map(btn => {
            return btn.textContent.replace('MRN ', '').trim();
        });
        
        if (mrnList.length === 0) {
            showStatusToast('No MRNs to copy', 'error');
            return;
        }
        
        const mrnText = mrnList.join(', ');
        
        navigator.clipboard.writeText(mrnText).then(() => {
            showStatusToast(`Copied ${mrnList.length} MRNs to clipboard ✓`, 'success');
        }).catch(err => {
            console.error('Failed to copy MRNs:', err);
            showStatusToast('Failed to copy MRNs', 'error');
        });
    }

    // Display workspace MRNs
    function displayWorkspace() {
        const includeContainer = document.getElementById('workspace-include-mrns');
        const excludeContainer = document.getElementById('workspace-exclude-mrns');
        const countSpan = document.getElementById('workspace-count');
        const includeCount = document.getElementById('include-count');
        const excludeCount = document.getElementById('exclude-count');
        
        const totalCount = cohortWorkspace.includeMRNs.length + cohortWorkspace.excludeMRNs.length;
        countSpan.textContent = `${totalCount} total`;
        includeCount.textContent = cohortWorkspace.includeMRNs.length;
        excludeCount.textContent = cohortWorkspace.excludeMRNs.length;
        
        // Display include MRNs
        if (cohortWorkspace.includeMRNs.length === 0) {
            includeContainer.innerHTML = '<em style="color: #999; font-size: 11px;">No MRNs included yet.</em>';
        } else {
            includeContainer.innerHTML = cohortWorkspace.includeMRNs.map((mrn, index) => {
                return `
                    <span class="workspace-mrn-chip" data-mrn="${mrn}" data-list="include" draggable="true">
                        ${mrn}<span class="workspace-chip-remove" onclick="removeFromWorkspace('include', ${index})">&times;</span>
                    </span>
                `;
            }).join('');
        }
        
        // Display exclude MRNs
        if (cohortWorkspace.excludeMRNs.length === 0) {
            excludeContainer.innerHTML = '<em style="color: #999; font-size: 11px;">No MRNs excluded yet.</em>';
        } else {
            excludeContainer.innerHTML = cohortWorkspace.excludeMRNs.map((mrn, index) => {
                return `
                    <span class="workspace-mrn-chip" data-mrn="${mrn}" data-list="exclude" draggable="true">
                        ${mrn}<span class="workspace-chip-remove" onclick="removeFromWorkspace('exclude', ${index})">&times;</span>
                    </span>
                `;
            }).join('');
        }
        
        // Setup drag-and-drop for newly created chips
        setupWorkspaceDragAndDrop();
    }

    // Remove MRN from workspace
    function removeFromWorkspace(listType, index) {
        if (listType === 'include') {
            cohortWorkspace.includeMRNs.splice(index, 1);
        } else if (listType === 'exclude') {
            cohortWorkspace.excludeMRNs.splice(index, 1);
        }
        saveWorkspace();
        displayWorkspace();
        updateMRNButtonStates();
    }

    // Clear entire workspace
    function clearWorkspace() {
        if (cohortWorkspace.includeMRNs.length === 0 && cohortWorkspace.excludeMRNs.length === 0) {
            return;
        }
        
        if (confirm('Clear all MRNs from workspace?')) {
            cohortWorkspace = { includeMRNs: [], excludeMRNs: [] };
            saveWorkspace();
            displayWorkspace();
            updateMRNButtonStates();
            showStatusToast('Workspace cleared', 'success');
        }
    }

    // Search Further - use only included MRNs
    function searchFurther() {
        if (cohortWorkspace.includeMRNs.length === 0) {
            showStatusToast('No MRNs in include list. Add some MRNs first.', 'error');
            return;
        }
        const form = document.querySelector("form");
        
        // Remove any existing workspace hidden fields
        clearWorkspaceHiddenFields(form);
        
        // Create hidden input with included MRNs only
        addHiddenFieldIfValue(form, 'mrns', cohortWorkspace.includeMRNs);
        
        // Submit the form immediately
        submitform(document.querySelector("form"));
    }

    // Search More (from workspace) - exclude all workspace MRNs
    function searchMoreExcludeAll() {
        const allWorkspaceMRNs = [...cohortWorkspace.includeMRNs, ...cohortWorkspace.excludeMRNs];
        
        if (allWorkspaceMRNs.length === 0) {
            showStatusToast('Workspace is empty. Add some MRNs first.', 'error');
            return;
        }
        
        const form = document.querySelector("form");
        
        // Remove any existing workspace hidden fields
        clearWorkspaceHiddenFields(form);
        
        // Clear the include MRN textarea
        const mrnsTextarea = document.getElementById('mrns-textarea');
        const originalInclude = mrnsTextarea.value;
    
        
        // Get existing excluded MRNs from visible textarea
        const mrnsExcludeTextarea = document.getElementById('mrns-exclude-textarea');
        const existingExclude = mrnsExcludeTextarea.value.trim();
        const existingMRNs = existingExclude ? existingExclude.split(/[,\s]+/).map(m => m.trim()).filter(m => m) : [];

        // Combine workspace MRNs with any existing excludes
        const allExcludedMRNs = [...new Set([...existingMRNs, ...allWorkspaceMRNs])];

        addHiddenFieldIfValue(form, 'mrns_exclude', allExcludedMRNs);
        
        // Submit the form 
        submitform(document.querySelector("form"));
    }

    // Save cohort to backend without doing a search

    function saveCohortToBackend() {
        if (cohortWorkspace.includeMRNs.length === 0 && cohortWorkspace.excludeMRNs.length === 0) {
            showStatusToast('No MRNs to save. Add some MRNs to workspace first.', 'error');
            return;
        }
        
        const form = document.querySelector("form");
        
        // Remove any existing workspace hidden fields
        clearWorkspaceHiddenFields(form);

        
        // Create hidden fields for include MRNs
        addHiddenFieldIfValue(form, 'mrns', cohortWorkspace.includeMRNs);
        
        // Create hidden fields for exclude MRNs
        addHiddenFieldIfValue(form, 'mrns_exclude', cohortWorkspace.excludeMRNs);
        
        // Add hidden field to indicate this is a save cohort action
        addHiddenField(form, 'save_cohort_action', 'yes');
        
        // Submit the form
        form.submit();
    }

    
    
    // ============================================
    // DRAG-AND-DROP FUNCTIONALITY FOR WORKSPACE
    // ============================================

    function setupWorkspaceDragAndDrop() {
        const chips = document.querySelectorAll('.workspace-mrn-chip');
        const containers = document.querySelectorAll('.workspace-mrns');
        
        chips.forEach(chip => {
            chip.addEventListener('dragstart', handleDragStart);
            chip.addEventListener('dragend', handleDragEnd);
        });
        
        containers.forEach(container => {
            container.addEventListener('dragover', handleDragOver);
            container.addEventListener('drop', handleDrop);
            container.addEventListener('dragleave', handleDragLeave);
        });
    }

    function handleDragStart(e) {
        e.target.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', e.target.innerHTML);
        e.dataTransfer.setData('mrn', e.target.dataset.mrn);
        e.dataTransfer.setData('sourceList', e.target.dataset.list);
    }

    function handleDragEnd(e) {
        e.target.classList.remove('dragging');
    }

    function handleDragOver(e) {
        if (e.preventDefault) {
            e.preventDefault();
        }
        e.dataTransfer.dropEffect = 'move';
        e.currentTarget.classList.add('drag-over');
        return false;
    }

    function handleDragLeave(e) {
        e.currentTarget.classList.remove('drag-over');
    }

    function handleDrop(e) {
        if (e.stopPropagation) {
            e.stopPropagation();
        }
        e.preventDefault();
        
        const mrn = e.dataTransfer.getData('mrn');
        const sourceList = e.dataTransfer.getData('sourceList');
        const targetList = e.currentTarget.getAttribute('data-list-type');
        
        e.currentTarget.classList.remove('drag-over');
        
        // Don't do anything if dropping on same list
        if (sourceList === targetList) {
            return false;
        }
        
        // Move MRN between lists
        if (sourceList === 'include' && targetList === 'exclude') {
            const index = cohortWorkspace.includeMRNs.indexOf(mrn);
            if (index > -1) {
                cohortWorkspace.includeMRNs.splice(index, 1);
                if (!cohortWorkspace.excludeMRNs.includes(mrn)) {
                    cohortWorkspace.excludeMRNs.push(mrn);
                }
            }
        } else if (sourceList === 'exclude' && targetList === 'include') {
            const index = cohortWorkspace.excludeMRNs.indexOf(mrn);
            if (index > -1) {
                cohortWorkspace.excludeMRNs.splice(index, 1);
                if (!cohortWorkspace.includeMRNs.includes(mrn)) {
                    cohortWorkspace.includeMRNs.push(mrn);
                }
            }
        }
        
        saveWorkspace();
        displayWorkspace();
        updateMRNButtonStates();
        
        return false;
    }

    // ============================================
    // KEYBOARD SHORTCUTS FOR MRN MANAGEMENT
    // ============================================

    // A = Add to Include, D = Add to Exclude
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey || e.altKey) return;

        // Only work when not in input/textarea
        const tag = e.target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) {
            return;
        }
        
        // Only handle A/D keys - check key first!
        if (e.key !== 'a' && e.key !== 'A' && e.key !== 'd' && e.key !== 'D') {
            return; // Not A or D, let other handlers deal with it
        }
        
        // Now check for active MRN button
        const activeMRNBtn = document.querySelector('#MRN-buttons button.active-MRN');
        if (!activeMRNBtn) return;

        e.preventDefault();
        
        const mrn = activeMRNBtn.textContent.replace('MRN ', '').trim();
        
        // A = Add to include list
        if (e.key === 'a' || e.key === 'A') {
            // e.preventDefault();
            
            // Remove from exclude if present
            const excludeIndex = cohortWorkspace.excludeMRNs.indexOf(mrn);
            if (excludeIndex > -1) {
                cohortWorkspace.excludeMRNs.splice(excludeIndex, 1);
            }
            
            // Add to include if not present
            if (!cohortWorkspace.includeMRNs.includes(mrn)) {
                cohortWorkspace.includeMRNs.push(mrn);
            } else {
                // Already in include list, remove it
                const includeIndex = cohortWorkspace.includeMRNs.indexOf(mrn);
                cohortWorkspace.includeMRNs.splice(includeIndex, 1);
            }
            
            saveWorkspace();
            displayWorkspace();
            updateMRNButtonStates();
            ensureWorkspaceExpanded();
        }
        
        // D = Add to exclude list
        if (e.key === 'd' || e.key === 'D') {
            // e.preventDefault();
            
            // Remove from include if present
            const includeIndex = cohortWorkspace.includeMRNs.indexOf(mrn);
            if (includeIndex > -1) {
                cohortWorkspace.includeMRNs.splice(includeIndex, 1);
            }
            
            // Add to exclude if not present
            if (!cohortWorkspace.excludeMRNs.includes(mrn)) {
                cohortWorkspace.excludeMRNs.push(mrn);
            } else {
                // Already in exclude list, remove it
                const excludeIndex = cohortWorkspace.excludeMRNs.indexOf(mrn);
                cohortWorkspace.excludeMRNs.splice(excludeIndex, 1);
            }
            
            saveWorkspace();
            displayWorkspace();
            updateMRNButtonStates();
            ensureWorkspaceExpanded();
        }
    });

    // Note display functions
    function scrollToHighlight(noteElement) {
        requestAnimationFrame(() => {
            const highlightElement = noteElement.querySelector(".highlight");
            const noteTextContainer = noteElement.querySelector(".note-text");
            
            if (highlightElement && noteTextContainer) {
                const containerRect = noteTextContainer.getBoundingClientRect();
                const highlightRect = highlightElement.getBoundingClientRect();
                const spaceAbove = 60;
                const currentScroll = noteTextContainer.scrollTop;
                const highlightRelativeTop = highlightRect.top - containerRect.top;
                const targetScroll = currentScroll + highlightRelativeTop - spaceAbove;
                noteTextContainer.scrollTop = Math.max(0, targetScroll);
            }
        });
    }

    function showMRN(MRN, btn) {
        document.querySelectorAll(".MRN-block").forEach(el => el.style.display = "none");
        const block = document.getElementById("MRN-" + MRN);
        if (block) {
            block.style.display = "block";
            const firstNote = block.querySelector(".note");
            if (firstNote) {
                block.querySelectorAll(".note").forEach(el => el.style.display = "none");
                firstNote.style.display = "block";
                scrollToHighlight(firstNote);
            }
            const firstNoteBtn = block.querySelector(".note-buttons button");
            if (firstNoteBtn) {
                block.querySelectorAll(".note-buttons button").forEach(b => b.classList.remove("active-note"));
                firstNoteBtn.classList.add("active-note");
            }
        }
        document.querySelectorAll("#MRN-buttons button").forEach(b => b.classList.remove("active-MRN"));
        if (btn) {
            btn.classList.add("active-MRN");
            const mrnButtonsContainer = document.getElementById('MRN-buttons');
            if (mrnButtonsContainer) {
                btn.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    }

    function showNote(MRN, idx, btn) {
    const block = document.getElementById("MRN-" + MRN);

    // Only hide notes for this MRN
    block.querySelectorAll(".note").forEach(el => el.style.display = "none");

    const note = document.getElementById("note-" + MRN + "-" + idx);
    if (note) {
        note.style.display = "block";
        scrollToHighlight(note);
    }

    block.querySelectorAll(".note-buttons button").forEach(b => b.classList.remove("active-note"));
    if (btn) {
        btn.classList.add("active-note");
        btn.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}


    // Initialize on page load
    document.addEventListener("DOMContentLoaded", () => {
        // start up pop up
        showStartupDisclaimer();

        // Load workspace from sessionStorage
        loadWorkspace();
        if (window.saveMessage && window.saveMessage.trim() !== '') {
            setTimeout(() => {
                showStatusToast(window.saveMessage, 'success');
            }, 500); // Small delay to ensure page is fully loaded
        }
    
        restoreFiltersFromURL();
        
        setupLeftColResizer();
        
        if (document.getElementById('mrn-resizer')) {
            setupMRNResizer();
        }
        
        if (document.querySelectorAll('.note-resizer').length > 0) {
            setupNoteResizers();
        }
        
        // Restore question card height if saved
        const savedQuestionHeight = localStorage.getItem('questionCardHeight');
        const questionCard = document.querySelector('.question-card');
        const filtersCard = document.getElementById('filters-card');
        if (savedQuestionHeight && questionCard && filtersCard) {
            questionCard.style.height = savedQuestionHeight + 'px';
            questionCard.style.flex = 'none';
            filtersCard.style.flex = '1 1 auto';
        }
        
        // Restore question textarea height
        const questionTextarea = document.getElementById('question-textarea');
        if (questionTextarea) {
            const savedTextareaHeight = localStorage.getItem('questionTextareaHeight');
            if (savedTextareaHeight) {
                questionTextarea.style.height = savedTextareaHeight + 'px';
            }
            
            questionTextarea.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = this.scrollHeight + 'px';
                localStorage.setItem('questionTextareaHeight', this.scrollHeight);
            });
            
            questionTextarea.style.height = 'auto';
            questionTextarea.style.height = questionTextarea.scrollHeight + 'px';
            if (!savedTextareaHeight) {
                localStorage.setItem('questionTextareaHeight', questionTextarea.scrollHeight);
            }
        }
        
        // Restore MRN include textarea height
        const mrnsTextarea = document.getElementById('mrns-textarea');
        if (mrnsTextarea) {
            const savedMrnsHeight = localStorage.getItem('mrnsTextareaHeight');
            if (savedMrnsHeight) {
                mrnsTextarea.style.height = savedMrnsHeight + 'px';
            }
            
            mrnsTextarea.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = this.scrollHeight + 'px';
                localStorage.setItem('mrnsTextareaHeight', this.scrollHeight);
            });
            
            mrnsTextarea.style.height = 'auto';
            mrnsTextarea.style.height = mrnsTextarea.scrollHeight + 'px';
            if (!savedMrnsHeight) {
                localStorage.setItem('mrnsTextareaHeight', mrnsTextarea.scrollHeight);
            }
        }
        
        // Restore MRN exclude textarea height
        const mrnsExcludeTextarea = document.getElementById('mrns-exclude-textarea');
        if (mrnsExcludeTextarea) {
            const savedMrnsExcludeHeight = localStorage.getItem('mrnsExcludeTextareaHeight');
            if (savedMrnsExcludeHeight) {
                mrnsExcludeTextarea.style.height = savedMrnsExcludeHeight + 'px';
            }
            
            mrnsExcludeTextarea.addEventListener('input', function() {
                this.style.height = 'auto';
                this.style.height = this.scrollHeight + 'px';
                localStorage.setItem('mrnsExcludeTextareaHeight', this.scrollHeight);
            });
            
            mrnsExcludeTextarea.style.height = 'auto';
            mrnsExcludeTextarea.style.height = mrnsExcludeTextarea.scrollHeight + 'px';
            if (!savedMrnsExcludeHeight) {
                localStorage.setItem('mrnsExcludeTextareaHeight', mrnsExcludeTextarea.scrollHeight);
            }
        }
        
        // Start with workspace collapsed on fresh startup, restore state during searches
        const urlParams = new URLSearchParams(window.location.search);
        const hasQueryParams = urlParams.toString().length > 0;
        const workspaceCollapsed = sessionStorage.getItem('workspaceCollapsed');
        const content = document.getElementById('workspace-content');
        const toggle = document.getElementById('workspace-toggle');
        const actions = document.getElementById('workspace-actions');
        
        if (!hasQueryParams) {
            // Fresh app startup - always start collapsed
            content.classList.add('collapsed');
            toggle.classList.add('collapsed');
            actions.classList.remove('show');
            sessionStorage.removeItem('workspaceCollapsed');
        } else if (workspaceCollapsed === null || workspaceCollapsed === 'true') {
            // Search result page - use saved state, default collapsed
            content.classList.add('collapsed');
            toggle.classList.add('collapsed');
            actions.classList.remove('show');
        } else {
            // User had it expanded in this session
            content.classList.remove('collapsed');
            toggle.classList.remove('collapsed');
            actions.classList.add('show');
        }
        
        // Show first MRN and note if results exist
        const firstMRN = document.querySelector(".MRN-block");
        const firstBtn = document.querySelector("#MRN-buttons button");
        if (firstMRN && firstBtn) {
            firstMRN.style.display = "block";
            const firstNote = firstMRN.querySelector(".note");
            if (firstNote) {
                firstNote.style.display = "block";
                scrollToHighlight(firstNote);
            }
            firstBtn.classList.add("active-MRN");
            const firstNoteBtn = firstMRN.querySelector(".note-buttons button");
            if (firstNoteBtn) firstNoteBtn.classList.add("active-note");
        }
        
        // Update MRN button states based on workspace
        updateMRNButtonStates();
        
        // Setup drag-and-drop for workspace
        setupWorkspaceDragAndDrop();


        // ==============================
        // MANAGE MODE BUTTON
        // ==============================
        const manageBtn = document.getElementById("manage-hint-btn");
        if (manageBtn) {
            manageBtn.addEventListener("click", () => {
                workspaceManageMode = !workspaceManageMode;
                updateMRNButtonStates();
            });
        }
        
        // ==============================
        // SAVE COHORT BUTTON
        // ==============================
        const saveCohortBtn = document.getElementById("save-cohort-btn");
        if (saveCohortBtn) {
            saveCohortBtn.addEventListener("click", () => {
                saveCohortToBackend();
            });
        }
    });

    // Load workspace from sessionStorage on page load
    function loadWorkspace() {
        // Check if this is a fresh app startup (no query parameters) or a search result page
        const urlParams = new URLSearchParams(window.location.search);
        const hasQueryParams = urlParams.toString().length > 0;
        
        if (!hasQueryParams) {
            // Fresh app startup - clear workspace
            cohortWorkspace = { includeMRNs: [], excludeMRNs: [] };
            sessionStorage.removeItem('cohortWorkspace');
            console.log('Fresh app startup - workspace cleared');
        } else {
            // Search result page - try to restore workspace from session
            const saved = sessionStorage.getItem('cohortWorkspace');
            if (saved) {
                try {
                    cohortWorkspace = JSON.parse(saved);
                    // Ensure arrays exist
                    if (!cohortWorkspace.includeMRNs) cohortWorkspace.includeMRNs = [];
                    if (!cohortWorkspace.excludeMRNs) cohortWorkspace.excludeMRNs = [];
                    console.log('Workspace restored from session:', cohortWorkspace.includeMRNs.length, 'include,', cohortWorkspace.excludeMRNs.length, 'exclude');
                } catch (e) {
                    console.error('Error loading workspace:', e);
                    cohortWorkspace = { includeMRNs: [], excludeMRNs: [] };
                }
            } else {
                // No saved workspace in session
                cohortWorkspace = { includeMRNs: [], excludeMRNs: [] };
                console.log(' No saved workspace found');
            }
        }
        
        displayWorkspace();
    }

    function updateWorkspaceSession() {
        try {
            sessionStorage.setItem('cohortWorkspace', JSON.stringify(cohortWorkspace));
        } catch (e) {
            console.error('Error updating workspace session:', e);
        }
    }


// ============================================
// KEYBOARD NAVIGATION
// ============================================
document.addEventListener("keydown", function (e) {
    const activeElement = document.activeElement;

    // -----------------------------
    // CMD+Enter or CTRL+Enter → SUBMIT SEARCH
    // -----------------------------
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        const askBtn = document.getElementById("ask-btn");
        if (askBtn) askBtn.click();
        return;
    }

    if (e.ctrlKey || e.metaKey) {
        return;
    }

    // Ignore arrow navigation if user is typing in an input/textarea
    if (activeElement && (activeElement.tagName === "INPUT" || activeElement.tagName === "TEXTAREA")) {
        return;
    }

    // -----------------------------
    // FOCUS SHORTCUTS (Q, I, E, F, C)
    // -----------------------------
    // Q = Focus Question box
    if (e.key === "q" || e.key === "Q") {
        e.preventDefault();
        const questionBox = document.getElementById("question-textarea");
        if (questionBox) {
            questionBox.focus();
            questionBox.select(); // Select all text for easy replacement
        }
        return;
    }

    // F = Jump to **Add Filter** button — not the Filters card
    if (e.key === "f" || e.key === "F") {
        e.preventDefault();
        const addFilterBtn = document.getElementById("add-filter-btn");
        if (addFilterBtn) {
            addFilterBtn.scrollIntoView({ behavior: "smooth", block: "center" });
            setTimeout(() => addFilterBtn.focus(), 120);
        }
        return;
    }


    // C = Jump to Cohort Workspace (auto-expand)
    if (e.key === "c" || e.key === "C") {
        e.preventDefault();

        const content = document.getElementById("workspace-content");
        const toggle = document.getElementById("workspace-toggle");
        const actions = document.getElementById("workspace-actions");

        // Auto-expand if collapsed
        if (content && content.classList.contains("collapsed")) {
            content.classList.remove("collapsed");
            toggle?.classList.remove("collapsed");
            actions?.classList.add("show");
            sessionStorage.setItem("workspaceCollapsed", "false");
        }

        const card = document.getElementById("workspace-card");
        if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return;
    }
    // M = Focus MRN list
    if (e.key === "m" || e.key === "M") {
        e.preventDefault();
        const firstMRN = document.querySelector("#MRN-buttons button");
        if (firstMRN) {
            firstMRN.focus();
            firstMRN.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        return;
    }

    // N = Focus first note button for current MRN
    if (e.key === "n" || e.key === "N") {
        e.preventDefault();

        const activeMRN = document.querySelector("#MRN-buttons button.active-MRN");
        if (!activeMRN) return;

        const mrn = activeMRN.textContent.replace(/^MRN\s+/, "").trim();
        const noteButtons = document.querySelectorAll(`#note-buttons-${mrn} button`);

        if (noteButtons.length > 0) {
            const firstNoteBtn = noteButtons[0];
            firstNoteBtn.focus();
            firstNoteBtn.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        return;
    }


    // -----------------------------
    // MRN NAVIGATION (Up / Down)
    // -----------------------------
    const mrnButtons = Array.from(document.querySelectorAll("#MRN-buttons button"));
    let currentMRNIndex = mrnButtons.findIndex(btn => btn.classList.contains("active-MRN"));

    // UP arrow = next MRN (move forward/right, higher index)
    if (e.key === "ArrowUp") {
        e.preventDefault();
        if (mrnButtons.length === 0) return;
        
        // If nothing selected, go to first
        if (currentMRNIndex === -1) {
            mrnButtons[0].click();
        }
        // Otherwise go to next, but don't wrap at the end
        else if (currentMRNIndex < mrnButtons.length - 1) {
            mrnButtons[currentMRNIndex + 1].click();
        }
        return;
    }

    // DOWN arrow = previous MRN (move backward/left, lower index)
    if (e.key === "ArrowDown") {
        e.preventDefault();
        if (mrnButtons.length === 0) return;
        
        // If nothing selected, go to first
        if (currentMRNIndex === -1) {
            mrnButtons[0].click();
        }
        // Otherwise go to previous, but don't wrap at the beginning
        else if (currentMRNIndex > 0) {
            mrnButtons[currentMRNIndex - 1].click();
        }
        return;
    }

    // -----------------------------
    // NOTE NAVIGATION (Left / Right)
    // Only handle if Left or Right was pressed
    // -----------------------------
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        console.log("=== ARROW KEY PRESSED ===");
        console.log("Key:", e.key);
        
        const activeMRNButton = document.querySelector("#MRN-buttons button.active-MRN");
        console.log("Active MRN button found:", activeMRNButton);
        
        if (!activeMRNButton) {
            console.warn("No active MRN button!");
            return;
        }

        // Get MRN more carefully - remove "MRN " prefix and trim any whitespace
        const buttonText = activeMRNButton.textContent;
        console.log("Button text:", JSON.stringify(buttonText));
        
        const mrn = buttonText.replace(/^MRN\s+/, "").trim();
        console.log("Extracted MRN:", JSON.stringify(mrn));
        
        // Try to find the note buttons container - escape special chars if needed
        const noteButtonsContainer = document.getElementById(`note-buttons-${mrn}`);
        console.log("Note buttons container:", noteButtonsContainer);
        console.log("Looking for ID:", `note-buttons-${mrn}`);
        
        if (!noteButtonsContainer) {
            console.error(`❌ Could not find note buttons container for MRN: "${mrn}"`);
            console.log("Available note button containers:");
            document.querySelectorAll('[id^="note-buttons-"]').forEach(el => {
                console.log("  -", el.id);
            });
            return;
        }
        
        const noteButtons = Array.from(noteButtonsContainer.querySelectorAll("button"));
        console.log(`Found ${noteButtons.length} note buttons`);
        noteButtons.forEach((btn, i) => {
            console.log(`  Button ${i}:`, btn.textContent, "Active?", btn.classList.contains("active-note"));
        });
        
        if (noteButtons.length === 0) {
            console.warn(`No note buttons found for MRN: ${mrn}`);
            return;
        }
        
        let currentNoteIndex = noteButtons.findIndex(btn => btn.classList.contains("active-note"));
        console.log("Current note index:", currentNoteIndex);

        // Right arrow = next note (higher index)
        if (e.key === "ArrowRight") {
            e.preventDefault();
            console.log("→ Going RIGHT");
            
            // If nothing selected, go to first
            if (currentNoteIndex === -1) {
                console.log("No note active, clicking first button");
                noteButtons[0].click();
            }
            // Otherwise go to next, but don't wrap at the end
            else if (currentNoteIndex < noteButtons.length - 1) {
                console.log(`Moving from note ${currentNoteIndex} to ${currentNoteIndex + 1}`);
                noteButtons[currentNoteIndex + 1].click();
            } else {
                console.log("Already at last note, not wrapping");
            }
            return;
        }

        // Left arrow = previous note (lower index)
        if (e.key === "ArrowLeft") {
            e.preventDefault();
            console.log("← Going LEFT");
            
            // If nothing selected, go to first
            if (currentNoteIndex === -1) {
                console.log("No note active, clicking first button");
                noteButtons[0].click();
            }
            // Otherwise go to previous, but don't wrap at the beginning
            else if (currentNoteIndex > 0) {
                console.log(`Moving from note ${currentNoteIndex} to ${currentNoteIndex - 1}`);
                noteButtons[currentNoteIndex - 1].click();
            } else {
                console.log("Already at first note, not wrapping");
            }
            return;
        }
    }
});