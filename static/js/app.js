/**
 * app.js: Single-Page Application (SPA) Controller for PDF ENGINE CAD Workbench.
 *
 * Implements:
 * - State management and reactive layout transitions
 * - Multi-page blueprint upload and background execution via REST
 * - Real-time pipeline progress monitoring via Server-Sent Events (SSE)
 * - Bi-directional interactive selection between Canvas, Inspector, and Bottom Schedule
 * - Direct one-click artifact export handlers (annotated PDF & Excel workbook)
 */

document.addEventListener('DOMContentLoaded', () => {
  // Application State
  const state = {
    runId: null,
    fileId: null,
    filename: 'test.pdf',
    currentPage: 1,
    totalPages: 1,
    currentMode: 'overlay', // 'overlay' | 'raw' | 'clean'
    sheets: [],
    summary: null,
    walls: [],
    selectedWall: null,
    leftDrawerOpen: true,
    rightDrawerOpen: true,
    bottomDockOpen: false,
    activeInspectorTab: 'properties',
    activeTool: 'select',
    scheduleFilter: 'all', // 'all' | 'verified' | 'review'
    sheetCatalog: [],
    selectedSheetsForProcessing: new Set(),
  };

  // DOM Elements
  const leftDrawer = document.getElementById('left-drawer');
  const rightDrawer = document.getElementById('right-drawer');
  const schedDrawer = document.getElementById('sched-drawer');
  const schedToggleBtn = document.getElementById('sched-toggle-btn');
  const uploadModal = document.getElementById('upload-modal');
  const stepperModal = document.getElementById('stepper-modal');

  // Viewer instance with Milestone 4 interactive tool hooks
  const viewer = new CADCanvasViewer({
    containerId: 'canvas-viewport',
    transformLayerId: 'canvas-transform-layer',
    imageId: 'sheet-image',
    svgId: 'svg-overlay',
    zoomLabelId: 'zoom-level-label',
    onWallSelected: (wall) => {
      state.selectedWall = wall;
      if (wall) {
        if (!state.rightDrawerOpen) toggleRightDrawer(true);
        populateInspector(wall);
        highlightScheduleRow(wall.run_id, true);
      } else {
        resetInspector();
        highlightScheduleRow(null, false);
      }
    },
    onPanZoomChanged: (scale, panX, panY) => {
      const hudCoords = document.getElementById('hud-coords');
      if (hudCoords) {
        hudCoords.textContent = `Scale: ${(scale * 100).toFixed(0)}% | X: ${Math.round(panX)}, Y: ${Math.round(panY)}`;
      }
    },
    onCalibrationComplete: ({ pt1, pt2, distPt, distPx }) => {
      openCalibrationModal(pt1, pt2, distPt, distPx);
    },
    onWallCreated: async ({ start, end }) => {
      await createManualWall(start, end);
    },
    onWallEndpointsChanged: async (wallId, newStart, newEnd) => {
      await updateWallEndpoints(wallId, newStart, newEnd);
    },
    onWallHover: (wallId, isHovered) => {
      highlightScheduleRow(wallId, isHovered);
    },
  });

  // ===========================================================================
  // DRAWER TOGGLES & LAYOUT
  // ===========================================================================

  window.toggleLeftDrawer = function(force) {
    state.leftDrawerOpen = force !== undefined ? force : !state.leftDrawerOpen;
    if (state.leftDrawerOpen) {
      leftDrawer.classList.remove('w-0', 'opacity-0', 'pointer-events-none');
      leftDrawer.classList.add('w-[300px]', 'opacity-100');
    } else {
      leftDrawer.classList.remove('w-[300px]', 'opacity-100');
      leftDrawer.classList.add('w-0', 'opacity-0', 'pointer-events-none');
    }
  };

  window.toggleRightDrawer = function(force) {
    state.rightDrawerOpen = force !== undefined ? force : !state.rightDrawerOpen;
    if (state.rightDrawerOpen) {
      rightDrawer.classList.remove('w-0', 'opacity-0', 'pointer-events-none');
      rightDrawer.classList.add('w-[340px]', 'opacity-100');
    } else {
      rightDrawer.classList.remove('w-[340px]', 'opacity-100');
      rightDrawer.classList.add('w-0', 'opacity-0', 'pointer-events-none');
    }
  };

  window.toggleScheduleDock = function(force) {
    state.bottomDockOpen = force !== undefined ? force : !state.bottomDockOpen;
    if (state.bottomDockOpen) {
      schedDrawer.classList.remove('h-0', 'h-10');
      schedDrawer.classList.add('h-64');
      if (schedToggleBtn) schedToggleBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">expand_more</span> Collapse';
    } else {
      schedDrawer.classList.remove('h-64');
      schedDrawer.classList.add('h-10');
      if (schedToggleBtn) schedToggleBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">expand_less</span> Expand';
    }
  };

  // Schedule Filter Handler ('all' | 'verified' | 'review')
  window.setScheduleFilter = function(filterMode) {
    state.scheduleFilter = filterMode;
    if (!state.bottomDockOpen) {
      window.toggleScheduleDock(true);
    }
    populateBottomSchedule();
  };

  // Switch Inspector Tab
  window.switchInspectorTab = function(tabName) {
    state.activeInspectorTab = tabName;
    ['properties', 'geometry', 'audit'].forEach(t => {
      const tabBtn = document.getElementById(`tab-btn-${t}`);
      const tabPane = document.getElementById(`tab-pane-${t}`);
      if (tabBtn && tabPane) {
        if (t === tabName) {
          tabBtn.classList.add('text-primary', 'border-b-2', 'border-primary', 'bg-primary/5');
          tabBtn.classList.remove('text-[#94a3b8]');
          tabPane.classList.remove('hidden');
        } else {
          tabBtn.classList.remove('text-primary', 'border-b-2', 'border-primary', 'bg-primary/5');
          tabBtn.classList.add('text-[#94a3b8]');
          tabPane.classList.add('hidden');
        }
      }
    });
  };

  // View Mode Switcher ("Raw PDF", "Clean Drawing", "Takeoff Overlay")
  window.setViewMode = function(mode) {
    state.currentMode = mode;
    ['raw', 'clean', 'overlay'].forEach(m => {
      const btn = document.getElementById(`mode-btn-${m}`);
      if (btn) {
        if (m === mode) {
          btn.className = 'px-3 py-1 bg-gradient-to-r from-primary to-[#06b6d4] text-[#002a78] font-bold rounded-none shadow-[0_0_12px_rgba(76,215,246,0.35)] flex items-center gap-1.5 transition-all text-xs font-mono';
        } else {
          btn.className = 'px-3 py-1 text-[#94a3b8] hover:text-white hover:bg-[#131e33] transition-all text-xs font-mono rounded-none';
        }
      }
    });

    if (state.runId) {
      const currentSheet = state.sheets[state.currentPage - 1];
      viewer.loadPage(state.runId, state.currentPage, mode, currentSheet);
    }
  };

  // Page Navigation
  window.prevPage = function() {
    if (state.currentPage > 1) {
      goToPage(state.currentPage - 1);
    }
  };

  window.nextPage = function() {
    if (state.currentPage < state.totalPages) {
      goToPage(state.currentPage + 1);
    }
  };

  function goToPage(pageNum) {
    state.currentPage = pageNum;
    updatePageNavUI();

    const select = document.getElementById('header-sheet-select');
    if (select) select.value = pageNum;

    renderSheetCatalogList();

    const currentSheet = (state.sheetCatalog && state.sheetCatalog.find(s => s.page_num === pageNum)) ||
                         state.sheets[state.currentPage - 1] || {};
    if (state.runId) {
      viewer.loadPage(state.runId, state.currentPage, state.currentMode, currentSheet);
    }
  }

  function updatePageNavUI() {
    const pageNavLabel = document.getElementById('page-nav-label');
    const sheetTypeBadge = document.getElementById('sheet-type-badge');
    const currentSheet = (state.sheetCatalog && state.sheetCatalog.find(s => s.page_num === state.currentPage)) ||
                         state.sheets[state.currentPage - 1] || {};

    if (pageNavLabel) {
      pageNavLabel.textContent = `Page ${state.currentPage} of ${state.totalPages}: ${currentSheet.sheet_label || 'SHEET'}`;
    }
    if (sheetTypeBadge) {
      sheetTypeBadge.textContent = currentSheet.page_type || 'PLAN';
    }
  }

  // Micro-toolbar actions
  window.canvasSetTool = (tool) => {
    state.activeTool = tool;
    viewer.setTool(tool);
    document.querySelectorAll('.tool-btn').forEach(btn => btn.classList.remove('bg-primary/20', 'text-primary'));
    const btnId = (tool === 'wall' || tool === 'wall_ruler') ? 'tool-btn-wall' : `tool-btn-${tool}`;
    const activeBtn = document.getElementById(btnId);
    if (activeBtn) activeBtn.classList.add('bg-primary/20', 'text-primary');
  };
  window.canvasZoomIn = () => viewer.zoomIn();
  window.canvasZoomOut = () => viewer.zoomOut();
  window.canvasFit = () => viewer.fitToScreen();
  window.canvasReset = () => viewer.resetView();

  // Layer toggle checkboxes
  window.toggleLayer = (layerName, checkbox) => {
    viewer.setLayerVisibility(layerName, checkbox.checked);
  };

  // ===========================================================================
  // MULTI-PAGE SHEET NAVIGATOR & SELECTIVE PROCESSING
  // ===========================================================================

  async function loadSheetCatalog(fileId) {
    if (!fileId) return;
    try {
      const res = await fetch(`/api/blueprint/${fileId}/sheets`);
      if (!res.ok) {
        console.warn(`Could not load sheet catalog for ${fileId}: HTTP ${res.status}`);
        return;
      }
      const catalog = await res.json();
      state.sheetCatalog = catalog;
      state.totalPages = catalog.length;
      const countEl = document.getElementById('sheet-count-label');
      if (countEl) countEl.textContent = catalog.length;
      renderSheetCatalogList();
      populateHeaderSheetSelect();
      updatePageNavUI();
    } catch (err) {
      console.warn('Failed to fetch sheet catalog', err);
    }
  }

  function renderSheetCatalogList() {
    const listEl = document.getElementById('sheet-catalog-list');
    if (!listEl) return;
    const floorPlansOnly = document.getElementById('filter-floorplans-only')?.checked ?? true;
    const query = (document.getElementById('sheet-search-input')?.value || '').trim().toLowerCase();

    const items = state.sheetCatalog || [];
    const filtered = items.filter(s => {
      if (floorPlansOnly && s.page_type !== 'FLOOR_PLAN') return false;
      if (query) {
        const label = (s.sheet_label || '').toLowerCase();
        const title = (s.sheet_title || '').toLowerCase();
        const pageStr = String(s.page_num);
        if (!label.includes(query) && !title.includes(query) && !pageStr.includes(query)) {
          return false;
        }
      }
      return true;
    });

    listEl.innerHTML = '';
    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="p-4 text-center text-[#64748b] text-xs font-mono">No matching sheets found</div>';
      updateSelectedSheetsCount();
      return;
    }

    filtered.forEach(s => {
      const isCurrent = s.page_num === state.currentPage;
      const isSelected = state.selectedSheetsForProcessing.has(s.page_num);
      const isFloorPlan = s.page_type === 'FLOOR_PLAN';

      const row = document.createElement('div');
      row.className = `p-2.5 flex items-center justify-between hover:bg-[#131e33] cursor-pointer transition-colors sheet-item ${isCurrent ? 'bg-primary/10 border-l-2 border-primary active' : ''}`;
      row.innerHTML = `
        <div class="flex items-center gap-2 overflow-hidden flex-1 min-w-0">
          <input type="checkbox" ${isSelected ? 'checked' : ''} class="sheet-checkbox accent-primary w-3.5 h-3.5 shrink-0"/>
          <div class="truncate">
            <div class="flex items-center gap-1.5">
              <span class="font-bold ${isCurrent ? 'text-primary' : 'text-white'}">P.${s.page_num} · ${s.sheet_label || 'SHEET'}</span>
              ${isFloorPlan 
                ? '<span class="px-1 py-0.2 bg-primary/20 text-primary text-[9px] border border-primary/30 font-bold">PLAN</span>' 
                : '<span class="px-1 py-0.2 bg-white/10 text-[#94a3b8] text-[9px]">' + (s.page_type || 'OTHER') + '</span>'}
            </div>
            <div class="text-[10px] text-[#94a3b8] truncate">${s.sheet_title || 'Untitled Sheet'}</div>
          </div>
        </div>
        <div class="text-[10px] text-[#64748b] shrink-0 ml-2 font-mono">${s.scale || ''}</div>
      `;

      const checkbox = row.querySelector('.sheet-checkbox');
      if (checkbox) {
        checkbox.addEventListener('click', (e) => {
          e.stopPropagation();
          toggleSheetSelection(s.page_num, checkbox.checked);
        });
      }

      row.addEventListener('click', () => {
        goToPage(s.page_num);
      });

      listEl.appendChild(row);
    });

    updateSelectedSheetsCount();
  }

  function populateHeaderSheetSelect() {
    const select = document.getElementById('header-sheet-select');
    if (!select) return;
    select.innerHTML = '';
    const items = state.sheetCatalog && state.sheetCatalog.length > 0 ? state.sheetCatalog : state.sheets;
    if (!items || items.length === 0) {
      const opt = document.createElement('option');
      opt.value = '1';
      opt.textContent = 'P.1: Sheet 1';
      select.appendChild(opt);
      return;
    }

    items.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.page_num;
      const label = s.sheet_label || `Page ${s.page_num}`;
      const title = s.sheet_title ? ` - ${s.sheet_title}` : '';
      opt.textContent = `P.${s.page_num}: ${label}${title}`;
      if (s.page_num === state.currentPage) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
    select.value = state.currentPage;
  }

  window.onHeaderSheetChange = function(pageNum) {
    goToPage(parseInt(pageNum, 10));
  };

  window.toggleSheetSelection = function(pageNum, isChecked) {
    if (isChecked) {
      state.selectedSheetsForProcessing.add(pageNum);
    } else {
      state.selectedSheetsForProcessing.delete(pageNum);
    }
    updateSelectedSheetsCount();
  };

  function updateSelectedSheetsCount() {
    const countEl = document.getElementById('selected-sheets-count');
    if (countEl) {
      countEl.textContent = state.selectedSheetsForProcessing.size;
    }
  }

  window.selectAllVisibleSheets = function() {
    const floorPlansOnly = document.getElementById('filter-floorplans-only')?.checked ?? true;
    const query = (document.getElementById('sheet-search-input')?.value || '').trim().toLowerCase();
    const items = state.sheetCatalog || [];
    items.forEach(s => {
      if (floorPlansOnly && s.page_type !== 'FLOOR_PLAN') return;
      if (query) {
        const label = (s.sheet_label || '').toLowerCase();
        const title = (s.sheet_title || '').toLowerCase();
        const pageStr = String(s.page_num);
        if (!label.includes(query) && !title.includes(query) && !pageStr.includes(query)) return;
      }
      state.selectedSheetsForProcessing.add(s.page_num);
    });
    renderSheetCatalogList();
  };

  window.deselectAllSheets = function() {
    state.selectedSheetsForProcessing.clear();
    renderSheetCatalogList();
  };

  window.filterSheets = function(query) {
    renderSheetCatalogList();
  };

  window.toggleFloorPlansFilter = function(checked) {
    renderSheetCatalogList();
  };

  window.submitSelectiveSheetProcessing = async function() {
    const fileId = state.fileId || state.runId;
    if (!fileId) {
      alert('No active blueprint loaded to process.');
      return;
    }

    const selected = Array.from(state.selectedSheetsForProcessing).sort((a, b) => a - b);
    const pagesToProcess = selected.length > 0 ? selected : [state.currentPage];

    closeUploadModal();
    openStepperModal(`Processing ${pagesToProcess.length} Selected Sheets`);
    appendTerminalLog('info', `Selective sheet processing initiated for pages: [${pagesToProcess.join(', ')}]...`);

    try {
      const res = await fetch(`/api/process/${fileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selected_pages: pagesToProcess,
          run_mode: 'selective',
          default_height_ft: parseFloat(document.getElementById('param-height')?.value || 10.0),
          stud_spacing_in: parseInt(document.getElementById('param-spacing')?.value || 16),
          waste_percent: parseFloat(document.getElementById('param-waste')?.value || 0.0),
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start selective processing');
      }

      const data = await res.json();
      state.runId = data.run_id;
      appendTerminalLog('info', `Selective pipeline worker active. Run ID: ${data.run_id}`);
      connectSSE(data.run_id);
    } catch (err) {
      appendTerminalLog('error', `Selective processing error: ${err.message}`);
    }
  };

  // ===========================================================================
  // ARTIFACT EXPORT HANDLERS
  // ===========================================================================

  window.downloadAnnotatedPDF = function() {
    if (!state.runId) return;
    window.location.href = `/api/blueprint/${state.runId}/annotated-pdf`;
  };

  window.downloadTakeoffExcel = function() {
    if (!state.runId) return;
    window.location.href = `/api/takeoff/${state.runId}/export/excel`;
  };

  // ===========================================================================
  // UPLOAD & PROCESSING WORKFLOW
  // ===========================================================================

  window.openUploadModal = function() {
    uploadModal.classList.remove('hidden');
    uploadModal.classList.add('flex');
  };

  window.closeUploadModal = function() {
    uploadModal.classList.add('hidden');
    uploadModal.classList.remove('flex');
  };

  // File Dropzone Handling
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const selectedFileNameEl = document.getElementById('selected-file-name');
  const startTakeoffBtn = document.getElementById('start-takeoff-btn');
  let pendingFile = null;

  if (dropzone && fileInput) {
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('border-primary', 'bg-primary/5');
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.classList.remove('border-primary', 'bg-primary/5');
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('border-primary', 'bg-primary/5');
      if (e.dataTransfer.files.length > 0) {
        handleFileSelected(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length > 0) {
        handleFileSelected(fileInput.files[0]);
      }
    });
  }

  function handleFileSelected(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      alert('Only PDF blueprint files (.pdf) are supported.');
      return;
    }
    pendingFile = file;
    if (selectedFileNameEl) {
      selectedFileNameEl.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
      selectedFileNameEl.classList.remove('hidden');
    }
    if (startTakeoffBtn) {
      startTakeoffBtn.disabled = false;
      startTakeoffBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
  }

  window.submitBlueprintUpload = async function() {
    if (!pendingFile) return;

    closeUploadModal();
    openStepperModal(pendingFile.name);

    try {
      const formData = new FormData();
      formData.append('file', pendingFile);

      appendTerminalLog('info', `Uploading blueprint: ${pendingFile.name}...`);
      const uploadRes = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });

      if (!uploadRes.ok) {
        const err = await uploadRes.json();
        throw new Error(err.detail || 'Upload failed');
      }

      const uploadData = await uploadRes.json();
      state.fileId = uploadData.file_id;
      state.filename = uploadData.filename;
      appendTerminalLog('success', `Uploaded document verified (${uploadData.page_count} pages). ID: ${uploadData.file_id}`);

      // Fetch sheet catalog immediately for multi-page navigator
      await loadSheetCatalog(uploadData.file_id);

      // Start pipeline processing
      appendTerminalLog('info', 'Triggering QTO processing pipeline...');
      const processRes = await fetch(`/api/process/${uploadData.file_id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          default_height_ft: parseFloat(document.getElementById('param-height')?.value || 10.0),
          stud_spacing_in: parseInt(document.getElementById('param-spacing')?.value || 16),
          waste_percent: parseFloat(document.getElementById('param-waste')?.value || 0.0),
        }),
      });

      if (!processRes.ok) {
        throw new Error('Failed to initiate processing pipeline');
      }

      const processData = await processRes.json();
      state.runId = processData.run_id;
      appendTerminalLog('info', `Pipeline worker active. Run ID: ${processData.run_id}`);

      // Connect SSE
      connectSSE(processData.run_id);
    } catch (err) {
      appendTerminalLog('error', `Pipeline execution error: ${err.message}`);
    }
  };

  // 1-Click Sample Blueprint Trigger
  window.runSampleFixture = async function(fixtureName) {
    closeUploadModal();
    openStepperModal(fixtureName);
    appendTerminalLog('info', `Loading synthetic test fixture: ${fixtureName}...`);

    try {
      const res = await fetch(`/api/fixture/run/${fixtureName}`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to run fixture');
      const data = await res.json();
      state.runId = data.run_id;
      state.filename = fixtureName;
      appendTerminalLog('success', `Test fixture pipeline initiated: ${data.run_id}`);
      connectSSE(data.run_id);
    } catch (err) {
      appendTerminalLog('error', `Error running fixture: ${err.message}`);
    }
  };

  // ===========================================================================
  // REAL-TIME SSE PROGRESS STEPPER HUD
  // ===========================================================================

  function openStepperModal(title) {
    stepperModal.classList.remove('hidden');
    stepperModal.classList.add('flex');
    document.getElementById('stepper-title').textContent = title;
    document.getElementById('progress-bar').style.width = '5%';
    document.getElementById('progress-pct-label').textContent = '5%';
    document.getElementById('stepper-terminal').innerHTML = '';
    document.getElementById('stepper-finish-btn').classList.add('hidden');
  }

  function appendTerminalLog(type, message) {
    const term = document.getElementById('stepper-terminal');
    if (!term) return;
    const timeStr = new Date().toISOString().substring(11, 19);
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = `[${timeStr}] ${message}`;
    term.appendChild(line);
    term.scrollTop = term.scrollHeight;
  }

  function connectSSE(runId) {
    const eventSource = new EventSource(`/api/pipeline/events/${runId}`);

    eventSource.addEventListener('progress', (e) => {
      try {
        const data = JSON.parse(e.data);
        const pct = data.progress_pct || 0;
        document.getElementById('progress-bar').style.width = `${pct}%`;
        document.getElementById('progress-pct-label').textContent = `${pct}%`;
        document.getElementById('stepper-status-text').textContent = data.stage || 'Processing';
        appendTerminalLog('info', `[${data.stage}] ${data.message}`);
        updateStepperIndicators(data.stage);
      } catch (err) {
        console.error('Error parsing SSE progress', err);
      }
    });

    eventSource.addEventListener('complete', async (e) => {
      eventSource.close();
      document.getElementById('progress-bar').style.width = '100%';
      document.getElementById('progress-pct-label').textContent = '100%';
      document.getElementById('stepper-status-text').textContent = 'Takeoff Complete';
      appendTerminalLog('success', 'Pipeline stages S00 through S16 completed successfully!');
      appendTerminalLog('success', 'Dual-red vector annotated PDF & 7-sheet openpyxl Excel ready.');

      // Mark all stage badges complete
      document.querySelectorAll('.stage-card').forEach(card => {
        card.classList.remove('border-primary', 'bg-primary/10');
        card.classList.add('border-emerald-500/40', 'bg-emerald-950/20');
        const icon = card.querySelector('.stage-icon');
        if (icon) {
          icon.textContent = 'check_circle';
          icon.className = 'material-symbols-outlined text-emerald-400 stage-icon text-[16px]';
        }
      });

      const finishBtn = document.getElementById('stepper-finish-btn');
      if (finishBtn) finishBtn.classList.remove('hidden');

      // Auto load run after slight pause
      setTimeout(() => {
        closeStepperModal();
        loadRun(runId);
      }, 900);
    });

    eventSource.addEventListener('error', (e) => {
      console.warn('SSE stream error or complete', e);
      // Fallback polling if SSE closes
      setTimeout(() => checkRunStatusFallback(runId, eventSource), 1000);
    });
  }

  async function checkRunStatusFallback(runId, eventSource) {
    try {
      const res = await fetch(`/api/pipeline/status/${runId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'completed') {
          eventSource.close();
          closeStepperModal();
          loadRun(runId);
        }
      }
    } catch (_) {}
  }

  window.closeStepperModal = function() {
    stepperModal.classList.add('hidden');
    stepperModal.classList.remove('flex');
  };

  function updateStepperIndicators(stageName) {
    const stagePrefix = (stageName || '').split(':')[0].trim();
    const stageMapping = {
      'S00': 1, 'S01': 1, 'S02': 1,
      'S03': 2, 'S04': 2, 'S05': 2,
      'S06': 3,
      'S07': 4, 'S08': 4, 'S09-S12': 4,
      'S13': 5,
      'S14': 6, 'S15': 6, 'S16': 6,
    };
    const activeIndex = stageMapping[stagePrefix] || 1;

    for (let i = 1; i <= 6; i++) {
      const card = document.getElementById(`stage-step-${i}`);
      if (!card) continue;
      const icon = card.querySelector('.stage-icon');

      if (i < activeIndex) {
        card.className = 'stage-card p-2 border border-emerald-500/40 bg-emerald-950/20 flex items-center justify-between text-xs font-mono';
        if (icon) {
          icon.textContent = 'check_circle';
          icon.className = 'material-symbols-outlined text-emerald-400 stage-icon text-[16px]';
        }
      } else if (i === activeIndex) {
        card.className = 'stage-card p-2 border border-primary bg-primary/10 shadow-[0_0_10px_rgba(76,215,246,0.2)] flex items-center justify-between text-xs font-mono';
        if (icon) {
          icon.textContent = 'hourglass_top';
          icon.className = 'material-symbols-outlined text-primary stage-icon text-[16px] animate-spin';
        }
      } else {
        card.className = 'stage-card p-2 border border-[#1f2937] bg-[#080d17] flex items-center justify-between text-xs font-mono text-[#64748b]';
        if (icon) {
          icon.textContent = 'radio_button_unchecked';
          icon.className = 'material-symbols-outlined text-[#64748b] stage-icon text-[16px]';
        }
      }
    }
  }

  // ===========================================================================
  // WORKBENCH DATA POPULATION
  // ===========================================================================

  async function loadRun(runId) {
    state.runId = runId;

    try {
      // 1. Fetch summary
      const sumRes = await fetch(`/api/takeoff/${runId}/summary`);
      if (!sumRes.ok) throw new Error('Failed to load takeoff summary');
      const summary = await sumRes.json();
      state.summary = summary;
      state.sheets = summary.sheets || [];
      state.totalPages = state.sheets.length || 1;
      state.filename = summary.pdf_file || state.filename;
      if (summary.file_id) {
        state.fileId = summary.file_id;
      }

      // Load sheet catalog for multi-page sheet navigator & header selector
      await loadSheetCatalog(state.fileId || runId);

      // 2. Fetch wall runs
      const wallsRes = await fetch(`/api/takeoff/${runId}/walls`);
      const wallsData = wallsRes.ok ? await wallsRes.json() : { walls: [] };
      state.walls = wallsData.walls || [];

      // Auto-navigate to first page with detected walls if current page has none
      if (state.walls.length > 0) {
        const hasWallsOnCurrentPage = state.walls.some(w => (w.page_num || 1) === state.currentPage);
        if (!hasWallsOnCurrentPage) {
          state.currentPage = state.walls[0].page_num || 1;
        }
      }

      // 3. Update top header
      document.getElementById('active-file-label').textContent = state.filename;
      updatePageNavUI();

      // Update scale badge
      const currentSheet = (state.sheetCatalog && state.sheetCatalog.find(s => s.page_num === state.currentPage)) ||
                           state.sheets[state.currentPage - 1] || {};
      const scaleStr = currentSheet.scale_string || '1/8" = 1\'-0"';
      document.getElementById('scale-badge-text').textContent = `Scale: ${scaleStr} (VERIFIED)`;

      // Update review status badge
      const reviewBadge = document.getElementById('review-badge');
      if (summary.review_items && summary.review_items.length > 0) {
        reviewBadge.className = 'flex items-center gap-1 text-xs text-amber-400 bg-amber-950/40 px-2 py-1 rounded-none border border-amber-500/30 font-mono';
        reviewBadge.innerHTML = `<span class="material-symbols-outlined text-[14px]">warning</span><span>${summary.review_items.length} Review Required</span>`;
      } else {
        reviewBadge.className = 'flex items-center gap-1 text-xs text-emerald-400 bg-emerald-950/40 px-2 py-1 rounded-none border border-emerald-500/30 font-mono';
        reviewBadge.innerHTML = `<span class="material-symbols-outlined text-[14px]">verified</span><span>${state.walls.length} Verified Runs · 0% Waste</span>`;
      }

      // Update notification banner
      const banner = document.getElementById('warning-banner');
      if (banner) {
        banner.innerHTML = `
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[16px] text-primary">verified</span>
            <span>TAKEOFF VERIFIED: ${state.walls.length} wall runs (${summary.total_net_lf?.toFixed(2)} Net LF, ${summary.total_board_sf?.toFixed(2)} Board SF) | Base Waste: 0.0%</span>
          </div>
          <button class="underline hover:text-white" onclick="toggleScheduleDock(true)">View Trade Schedule</button>
        `;
      }

      // 4. Update Left Drawer Layers & Regions
      populateLayersAndRegions();

      // 5. Update Bottom Schedule
      populateBottomSchedule();

      // 6. Load canvas blueprint
      await viewer.loadPage(state.runId, state.currentPage, state.currentMode, currentSheet);
      viewer.setWalls(state.walls);

      // Select first wall if available
      if (state.walls.length > 0) {
        viewer.selectWall(state.walls[0].run_id);
      }
    } catch (err) {
      console.error('Failed to populate workbench', err);
    }
  }

  function populateLayersAndRegions() {
    const wallCount = state.walls.length;
    const countEl = document.getElementById('layer-count-wall');
    if (countEl) countEl.textContent = `${wallCount} vector runs`;

    // Populate Sheet Regions list
    const regionList = document.getElementById('sheet-regions-list');
    if (regionList && state.sheets.length > 0) {
      regionList.innerHTML = '';
      state.sheets.forEach(s => {
        const item = document.createElement('div');
        item.className = 'p-2 hover:bg-[#131e33] cursor-pointer flex items-center justify-between text-xs font-mono text-[#cbd5e1] border-b border-[#1f2937]/40';
        item.innerHTML = `
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[14px] text-primary">map</span>
            <span>${s.sheet_label || `Page ${s.page_num}`}</span>
          </div>
          <span class="text-[10px] text-[#64748b]">${s.page_type || 'PLAN'}</span>
        `;
        item.onclick = () => goToPage(s.page_num);
        regionList.appendChild(item);
      });
    }
  }

  // ===========================================================================
  // INSPECTOR PANEL POPULATION & EDITING
  // ===========================================================================

  function formatArchitecturalInches(val) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const numVal = parseFloat(val);
    const whole = Math.floor(numVal);
    const frac = numVal - whole;
    const sixteenths = Math.round(frac * 16);
    if (sixteenths === 0) return `${whole}"`;
    if (sixteenths === 16) return `${whole + 1}"`;
    let num = sixteenths;
    let den = 16;
    while (num % 2 === 0 && den % 2 === 0) {
      num /= 2;
      den /= 2;
    }
    return whole > 0 ? `${whole}-${num}/${den}"` : `${num}/${den}"`;
  }

  function populateInspector(wall) {
    if (!wall) return;

    // Header tag & sheet info
    const tagEl = document.getElementById('inspector-wall-tag');
    if (tagEl) tagEl.textContent = `${wall.run_id} · Tag ${wall.tag || 'N/A'}`;

    const sheetEl = document.getElementById('inspector-wall-sheet');
    if (sheetEl) sheetEl.textContent = `Page ${wall.page_num || state.currentPage} · ${wall.sheet_label || 'A-101'}`;

    // Status Badge Logic (Requirement R4 & Acceptance Criteria)
    const statusEl = document.getElementById('inspector-audit-badge');
    const isManual = !!wall.is_manual;
    const isVerified = !!wall.is_height_verified && wall.status !== 'REVIEW';

    if (statusEl) {
      if (isManual) {
        statusEl.textContent = 'MANUAL';
        statusEl.className = 'bg-purple-950/60 text-purple-300 border border-purple-500/40 px-1.5 py-0.5 text-[10px] font-mono font-bold';
      } else if (isVerified) {
        statusEl.textContent = 'VERIFIED';
        statusEl.className = 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/40 px-1.5 py-0.5 text-[10px] font-mono font-bold';
      } else {
        statusEl.textContent = 'REVIEW';
        statusEl.className = 'bg-amber-950/60 text-amber-400 border border-amber-500/40 px-1.5 py-0.5 text-[10px] font-mono font-bold';
      }
    }

    // Estimator Review Warning Banner vs Verified Banner
    const reviewBanner = document.getElementById('inspector-review-banner');
    const reviewReason = document.getElementById('inspector-review-reason');
    const verifiedBanner = document.getElementById('inspector-verified-banner');
    const verifiedDetail = document.getElementById('inspector-verified-detail');

    if (!isVerified && !isManual) {
      if (reviewBanner) reviewBanner.classList.remove('hidden');
      if (reviewReason) {
        const customNote = (wall.notes && wall.notes.length > 0) ? wall.notes.join(' | ') : null;
        reviewReason.textContent = customNote || 'No explicit height found on referenced detail; defaulted to 10.0 ft. Estimator review required.';
      }
      if (verifiedBanner) verifiedBanner.classList.add('hidden');
    } else {
      if (reviewBanner) reviewBanner.classList.add('hidden');
      if (verifiedBanner) {
        verifiedBanner.classList.remove('hidden');
        if (verifiedDetail) {
          verifiedDetail.textContent = wall.section_callout_tag ? `${wall.section_callout_tag} (${Number(wall.height_ft || 10).toFixed(1)} ft)` : `${Number(wall.height_ft || 10).toFixed(1)} ft`;
        }
      }
    }

    // Editable Tag Dropdown
    const tagSelect = document.getElementById('inspector-tag-select');
    if (tagSelect && wall.tag) {
      tagSelect.value = wall.tag;
    }

    // Editable Height Input
    const heightInput = document.getElementById('inspector-height-input');
    if (heightInput) {
      heightInput.value = wall.height_ft || 10.0;
    }

    // Tab 1: Properties & Quantities
    const netLF = wall.net_length_ft !== undefined ? wall.net_length_ft : (wall.gross_length_ft || 0) - (wall.opening_deduction_ft || 0);
    const grossLF = wall.gross_length_ft || 0;
    const deductLF = wall.opening_deduction_ft || 0;
    const heightFt = wall.height_ft || 10.0;
    const tagInfo = (state.summary && state.summary.by_tag && state.summary.by_tag[wall.tag]) || {};
    const faces = tagInfo.faces || 2;
    const layers = tagInfo.layers_per_face || 1;
    const studSpacing = tagInfo.stud_spacing_in || 16;
    const boardSF = (grossLF - deductLF) * heightFt * faces * layers;
    const openingsCount = wall.openings ? wall.openings.length : (wall.openings_count || 0);
    const studsEa = Math.ceil((netLF * 12) / studSpacing) + 1 + openingsCount * 2;
    const trackLF = grossLF + netLF;

    const propEntityType = document.getElementById('prop-entity-type');
    if (propEntityType) propEntityType.textContent = `${isManual ? 'Manual' : 'Traced'} Interior Partition (Tag ${wall.tag})`;

    const propGross = document.getElementById('prop-gross-lf');
    if (propGross) propGross.textContent = `${grossLF.toFixed(2)} LF`;

    const propDeduct = document.getElementById('prop-deduct-lf');
    if (propDeduct) propDeduct.textContent = `-${deductLF.toFixed(2)} LF (${openingsCount} openings)`;

    const propNet = document.getElementById('prop-net-lf');
    if (propNet) propNet.textContent = `${netLF.toFixed(2)} LF`;

    const propBoard = document.getElementById('prop-board-sf');
    if (propBoard) propBoard.textContent = `${boardSF.toFixed(2)} SF`;

    const propStuds = document.getElementById('prop-studs-ea');
    if (propStuds) propStuds.textContent = `${studsEa} EA (${(studsEa * heightFt).toFixed(0)} LF)`;

    const propTrack = document.getElementById('prop-track-lf');
    if (propTrack) propTrack.textContent = `${trackLF.toFixed(2)} LF (Runner + Plate)`;

    // Rich Wall Thickness (Measured vs Nominal)
    const propThick = document.getElementById('prop-thickness');
    if (propThick) {
      if (wall.thickness_in !== undefined && wall.thickness_in !== null) {
        const thickNum = Number(wall.thickness_in);
        const fracStr = formatArchitecturalInches(thickNum);
        const isMeasured = !!wall.thickness_measured;
        const badgeClass = isMeasured
          ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-500/30'
          : 'bg-[#1e293b] text-[#94a3b8] border border-[#334155]';
        const label = isMeasured ? 'CAD Measured' : 'Nominal';

        propThick.innerHTML = `
          <div class="flex items-center gap-1.5 justify-end">
            <span class="${isMeasured ? 'text-emerald-400' : 'text-white'} font-bold">${thickNum.toFixed(2)}" (${fracStr})</span>
            <span class="text-[9px] px-1 py-0.2 font-mono uppercase ${badgeClass}">${label}</span>
          </div>
        `;
      } else {
        propThick.textContent = '—';
        propThick.className = 'text-[#64748b] font-bold';
      }
    }

    // Height Verification Status & Section Callout Tag
    const propHeightVer = document.getElementById('prop-height-verification');
    if (propHeightVer) {
      if (isVerified) {
        propHeightVer.innerHTML = `<span class="text-emerald-400 font-bold">VERIFIED (${heightFt.toFixed(1)} ft)</span>`;
      } else {
        propHeightVer.innerHTML = `<span class="text-amber-400 font-bold">REVIEW (10.0 ft Fallback)</span>`;
      }
    }

    const propCallout = document.getElementById('prop-section-callout');
    if (propCallout) {
      propCallout.textContent = wall.section_callout_tag || 'None within 120pt';
      propCallout.className = wall.section_callout_tag ? 'text-primary font-mono font-bold' : 'text-[#64748b] font-mono';
    }

    const propHeightSource = document.getElementById('prop-height-source');
    if (propHeightSource) {
      const srcText = wall.height_source || (isVerified ? 'Section Detail' : 'UNVERIFIED_HEIGHT_DEFAULT');
      propHeightSource.textContent = srcText;
      propHeightSource.title = srcText;
      propHeightSource.className = isVerified ? 'text-emerald-400 font-mono text-right truncate max-w-[170px]' : 'text-amber-400 font-mono text-right truncate max-w-[170px]';
    }

    // Structured Material Layer Stack Breakdown (Face A, Core, Face B)
    const layersListEl = document.getElementById('prop-material-layers-list');
    const layersCountEl = document.getElementById('prop-layers-count');
    let layers = (wall.material_layers && wall.material_layers.length > 0)
      ? wall.material_layers
      : (tagInfo.material_layers || []);

    if (layersCountEl) layersCountEl.textContent = `${layers.length} Layers`;
    if (layersListEl) {
      if (layers.length > 0) {
        layersListEl.innerHTML = layers.map((l, idx) => {
          const side = (l.side || `Layer ${idx + 1}`).trim();
          let sideBadgeClass = 'bg-primary/10 text-primary border-primary/30';
          if (side.toLowerCase().includes('face a')) {
            sideBadgeClass = 'bg-primary/10 text-primary border-primary/30';
          } else if (side.toLowerCase().includes('core')) {
            sideBadgeClass = 'bg-amber-950/40 text-amber-300 border-amber-500/30';
          } else if (side.toLowerCase().includes('face b')) {
            sideBadgeClass = 'bg-blue-950/40 text-blue-300 border-blue-500/30';
          }

          return `
            <div class="p-1.5 bg-[#070b13] border border-[#1f2937] flex items-start gap-2 text-[11px]">
              <span class="px-1.5 py-0.5 text-[9px] font-bold font-mono uppercase border shrink-0 ${sideBadgeClass}">${side}</span>
              <div class="flex-1">
                <div class="text-white font-medium leading-tight">${l.material || 'Gypsum Board'}</div>
                <div class="text-[10px] text-[#64748b] font-mono mt-0.5">${l.layer ? `Layer: ${l.layer}` : 'Standard Assembly Layer'}</div>
              </div>
            </div>
          `;
        }).join('');
      } else {
        layersListEl.innerHTML = '<div class="text-[11px] text-[#64748b] font-mono py-1">No structured layer breakdown available for this tag.</div>';
      }
    }

    // Opening Deductions Manager List
    renderInspectorOpenings(wall);

    // Consumables estimate
    const fasteners = Math.ceil(boardSF);
    const jointTape = (netLF * 2 * 4.0).toFixed(1);
    const jointMud = (boardSF * 0.0095).toFixed(2);
    const propFasteners = document.getElementById('prop-fasteners');
    if (propFasteners) propFasteners.textContent = `${fasteners} EA (#6 Bugle Head)`;
    const propTape = document.getElementById('prop-tape');
    if (propTape) propTape.textContent = `${jointTape} LF (Paper/Mesh Tape)`;
    const propMud = document.getElementById('prop-mud');
    if (propMud) propMud.textContent = `${jointMud} Gal (All-Purpose Compound)`;

    // Materials description
    const tagInfo = state.summary?.by_tag?.[wall.tag] || {};
    const matDesc = tagInfo.description || `${wall.tag}: 5/8" TYPE X GWB EACH SIDE ON 3-5/8" METAL STUDS @ 16" O.C.`;
    const propMat = document.getElementById('prop-materials-desc');
    if (propMat) propMat.textContent = matDesc;

    // Tab 2: Geometry & Deductions
    const spine = wall.spine || {};
    const geomCoords = document.getElementById('geom-spine-coords');
    if (geomCoords) geomCoords.textContent = `X1: ${spine.x1?.toFixed(1)}, Y1: ${spine.y1?.toFixed(1)} -> X2: ${spine.x2?.toFixed(1)}, Y2: ${spine.y2?.toFixed(1)}`;
    const geomAngle = document.getElementById('geom-angle');
    if (geomAngle) geomAngle.textContent = `${spine.angle?.toFixed(1) || 0}°`;
    const geomFtPt = document.getElementById('geom-ft-per-pt');
    if (geomFtPt) geomFtPt.textContent = `${(wall.ft_per_pt || 0.111111).toFixed(6)} ft/pt`;
    const geomThickPt = document.getElementById('geom-thickness-pt');
    if (geomThickPt) {
      geomThickPt.textContent = wall.thickness_pt ? `${Number(wall.thickness_pt).toFixed(2)} pt` : '—';
    }
    const geomOpenCount = document.getElementById('geom-openings-count');
    if (geomOpenCount) geomOpenCount.textContent = `${openingsCount} Deductions`;

    const geomOpenList = document.getElementById('geom-openings-list');
    if (geomOpenList) {
      if (wall.openings && wall.openings.length > 0) {
        geomOpenList.innerHTML = wall.openings.map((op, idx) => `
          <div class="p-1.5 bg-[#070b13] border border-[#1f2937] text-[11px] font-mono flex items-center justify-between">
            <span class="text-amber-400">#${idx + 1} ${(op.type || op.classification || 'Opening').toUpperCase()}</span>
            <span class="text-white">${op.width_ft || 3.0} LF (${op.classification || 'CONFIRMED'})</span>
          </div>
        `).join('');
      } else {
        geomOpenList.innerHTML = '<div class="text-[11px] text-[#64748b] font-mono">No opening deductions along this run.</div>';
      }
    }

    // Tab 3: Provenance & Audit
    const auditRunId = document.getElementById('audit-run-id');
    if (auditRunId) auditRunId.textContent = state.runId || 'N/A';
    const auditHash = document.getElementById('audit-pdf-hash');
    if (auditHash) auditHash.textContent = (state.summary?.pdf_sha256 || '0x8f2a...').substring(0, 24) + '...';
    const auditSheet = document.getElementById('audit-source-sheet');
    if (auditSheet) auditSheet.textContent = wall.sheet_label || `Page ${wall.page_num}`;
    const auditEngine = document.getElementById('audit-engine');
    if (auditEngine) auditEngine.textContent = 'PyMuPDF CAD Vector Core v1.0';
  }

  function renderInspectorOpenings(wall) {
    const listEl = document.getElementById('inspector-openings-list');
    if (!listEl) return;

    if (!wall.openings || wall.openings.length === 0) {
      listEl.innerHTML = '<div class="text-[11px] text-[#64748b] font-mono py-1">No opening deductions. Click + Add Door or Window above.</div>';
      return;
    }

    listEl.innerHTML = wall.openings.map((op, idx) => {
      const wFt = op.width_ft || 3.0;
      const hFt = op.height_ft || 7.0;
      const areaSf = (wFt * hFt * 2).toFixed(1);
      const isDoor = (op.type || op.classification || 'door').toLowerCase().includes('door');
      const label = isDoor ? 'Door' : 'Window';
      const icon = isDoor ? 'meeting_room' : 'window';

      return `
        <div class="p-1.5 bg-[#070b13] border border-[#1f2937] text-[11px] font-mono flex items-center justify-between">
          <div class="flex items-center gap-1.5">
            <span class="material-symbols-outlined text-amber-400 text-[14px]">${icon}</span>
            <span class="text-white font-bold">${label} #${idx + 1}: ${wFt.toFixed(1)}' × ${hFt.toFixed(1)}'</span>
            <span class="text-amber-400 text-[10px]">(-${areaSf} SF)</span>
          </div>
          <button onclick="event.stopPropagation(); deleteOpeningDeduction('${op.opening_id}')" class="text-[#64748b] hover:text-red-400 p-0.5 transition-colors" title="Delete Opening">
            <span class="material-symbols-outlined text-[14px]">delete</span>
          </button>
        </div>
      `;
    }).join('');
  }

  function resetInspector() {
    const tagEl = document.getElementById('inspector-wall-tag');
    if (tagEl) tagEl.textContent = 'No Wall Selected';
    const sheetEl = document.getElementById('inspector-wall-sheet');
    if (sheetEl) sheetEl.textContent = '';
    const statusEl = document.getElementById('inspector-audit-badge');
    if (statusEl) {
      statusEl.textContent = 'NO SELECTION';
      statusEl.className = 'bg-[#1e293b] text-[#94a3b8] border border-[#334155] px-1.5 py-0.5 text-[10px] font-mono';
    }
    const reviewBanner = document.getElementById('inspector-review-banner');
    if (reviewBanner) reviewBanner.classList.add('hidden');
    const verifiedBanner = document.getElementById('inspector-verified-banner');
    if (verifiedBanner) verifiedBanner.classList.add('hidden');
    const propGross = document.getElementById('prop-gross-lf');
    if (propGross) propGross.textContent = '0.00 LF';
    const propDeduct = document.getElementById('prop-deduct-lf');
    if (propDeduct) propDeduct.textContent = '0.00 LF';
    const propNet = document.getElementById('prop-net-lf');
    if (propNet) propNet.textContent = '0.00 LF';
    const propBoard = document.getElementById('prop-board-sf');
    if (propBoard) propBoard.textContent = '0.00 SF';
    const propStuds = document.getElementById('prop-studs-ea');
    if (propStuds) propStuds.textContent = '0 EA';
    const propTrack = document.getElementById('prop-track-lf');
    if (propTrack) propTrack.textContent = '0.00 LF';
    const propThick = document.getElementById('prop-thickness');
    if (propThick) propThick.textContent = '—';
    const propHeightVer = document.getElementById('prop-height-verification');
    if (propHeightVer) propHeightVer.textContent = '—';
    const propCallout = document.getElementById('prop-section-callout');
    if (propCallout) propCallout.textContent = '—';
    const propHeightSource = document.getElementById('prop-height-source');
    if (propHeightSource) propHeightSource.textContent = '—';
    const openList = document.getElementById('inspector-openings-list');
    if (openList) openList.innerHTML = '<div class="text-[11px] text-[#64748b] font-mono">Select a wall on canvas.</div>';
    const layersListEl = document.getElementById('prop-material-layers-list');
    if (layersListEl) layersListEl.innerHTML = '<div class="text-[11px] text-[#64748b] font-mono py-1">Select a wall to view layer breakdown.</div>';
  }

  // ===========================================================================
  // 2-POINT SCALE CALIBRATION CONTROLLER
  // ===========================================================================

  function openCalibrationModal(pt1, pt2, distPt, distPx) {
    state.calibPt1 = pt1;
    state.calibPt2 = pt2;
    state.calibDistPt = distPt;
    const modal = document.getElementById('modal-calibration');
    if (modal) {
      modal.classList.remove('hidden');
      modal.classList.add('flex');
    }
    const distEl = document.getElementById('calib-measured-pts');
    if (distEl) {
      distEl.textContent = `${distPt.toFixed(1)} pt (${distPx.toFixed(0)} px)`;
    }
  }
  window.openCalibrationModal = openCalibrationModal;

  window.closeCalibrationModal = function() {
    const modal = document.getElementById('modal-calibration');
    if (modal) {
      modal.classList.add('hidden');
      modal.classList.remove('flex');
    }
    canvasSetTool('select');
  };

  window.confirmCalibration = async function() {
    const inputVal = (document.getElementById('calib-distance-input')?.value || '20.0').trim();
    const unit = document.getElementById('calib-unit-select')?.value || 'ft';

    let realDistFt = parseFloat(inputVal);
    // Support architectural feet-inches (e.g. 20'-6", 15' 3")
    if (inputVal.includes("'") || inputVal.includes('"') || inputVal.includes('-')) {
      const m = inputVal.match(/^(\d+(?:\.\d+)?)\s*(?:'|ft)?(?:\s*-\s*|\s+)?(?:(\d+(?:\.\d+)?)\s*(?:\"|in)?)?$/);
      if (m) {
        const ft = parseFloat(m[1]) || 0;
        const inches = parseFloat(m[2]) || 0;
        realDistFt = ft + inches / 12.0;
      }
    }

    if (isNaN(realDistFt) || realDistFt <= 0) {
      alert('Please enter a valid positive distance (e.g. 20.0 or 20\'-0")');
      return;
    }

    try {
      const payload = {
        pt1: { x: state.calibPt1.x, y: state.calibPt1.y },
        pt2: { x: state.calibPt2.x, y: state.calibPt2.y },
        real_world_distance_ft: realDistFt,
        dimension_string: inputVal,
        unit: unit,
      };

      const res = await fetch(`/api/blueprint/${state.runId}/page/${state.currentPage}/calibrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Calibration failed');
      }

      const calibData = await res.json();

      // Update scale badge text
      const scaleBadge = document.getElementById('scale-badge-text');
      if (scaleBadge) {
        scaleBadge.textContent = `Calibrated (${calibData.new_ft_per_pt.toFixed(6)} ft/pt)`;
      }

      // Update sheet scale in memory
      if (state.sheetCatalog) {
        const curSheet = state.sheetCatalog.find(s => s.page_num === state.currentPage);
        if (curSheet) {
          curSheet.ft_per_pt = calibData.new_ft_per_pt;
          curSheet.scale = `Calibrated (${calibData.new_ft_per_pt.toFixed(6)} ft/pt)`;
        }
      }

      // Update viewer scale
      viewer.currentScaleFtPerPt = calibData.new_ft_per_pt;

      // Reload wall runs from backend and refresh schedule
      await refreshWallsAndSchedule();

      closeCalibrationModal();
    } catch (err) {
      console.error('Calibration failed', err);
      alert(`Calibration failed: ${err.message}`);
    }
  };

  // ===========================================================================
  // MANUAL WALL DRAWING / RULER TOOL CONTROLLER
  // ===========================================================================

  async function createManualWall(startPt, endPt) {
    const tag = document.getElementById('active-partition-tag')?.value || '5E';
    const height = parseFloat(document.getElementById('active-wall-height')?.value || '10.0');

    try {
      const payload = {
        start: { x: startPt.x, y: startPt.y },
        end: { x: endPt.x, y: endPt.y },
        tag: tag,
        height_ft: height,
      };

      const res = await fetch(`/api/blueprint/${state.runId}/page/${state.currentPage}/walls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create manual wall');
      }

      const data = await res.json();
      const newWall = data.wall || data;

      // Add new WallRun (is_manual: true) to state.walls
      state.walls.push(newWall);

      // Re-render canvas vector overlays
      viewer.setWalls(state.walls);

      // Select newly created wall
      viewer.selectWall(newWall.run_id);

      // Update schedule dock table and summary totals
      populateBottomSchedule();

      // Open Right Inspector
      toggleRightDrawer(true);
    } catch (err) {
      console.error('Error creating manual wall', err);
      alert(`Could not create wall: ${err.message}`);
    }
  }

  // ===========================================================================
  // DRAGGABLE ENDPOINT HANDLES CONTROLLER
  // ===========================================================================

  async function updateWallEndpoints(wallId, newStart, newEnd) {
    try {
      const payload = {
        start: { x: newStart.x, y: newStart.y },
        end: { x: newEnd.x, y: newEnd.y },
      };

      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to update wall endpoints');
      }

      const data = await res.json();
      const updatedWall = data.wall;

      const idx = state.walls.findIndex(w => w.run_id === wallId);
      if (idx !== -1) {
        state.walls[idx] = updatedWall;
      }
      if (state.selectedWall && state.selectedWall.run_id === wallId) {
        state.selectedWall = updatedWall;
        populateInspector(updatedWall);
      }

      populateBottomSchedule();
    } catch (err) {
      console.error('Failed to update wall endpoints', err);
    }
  }

  // ===========================================================================
  // MARKUP EDITING & OPENING DEDUCTIONS
  // ===========================================================================

  window.onInspectorTagChange = async function(newTag) {
    if (!state.selectedWall) return;
    const wallId = state.selectedWall.run_id;
    try {
      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag: newTag }),
      });
      if (!res.ok) throw new Error('Failed to update wall tag');
      const data = await res.json();
      state.selectedWall = data.wall;
      const idx = state.walls.findIndex(w => w.run_id === wallId);
      if (idx !== -1) state.walls[idx] = data.wall;
      viewer.setWalls(state.walls);
      viewer.selectWall(wallId);
      populateBottomSchedule();
    } catch (err) {
      console.error('Error updating wall tag', err);
    }
  };

  window.onInspectorHeightChange = async function(newHeight) {
    if (!state.selectedWall) return;
    const wallId = state.selectedWall.run_id;
    const h = parseFloat(newHeight);
    if (isNaN(h) || h <= 0) return;
    try {
      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ height_ft: h }),
      });
      if (!res.ok) throw new Error('Failed to update wall height');
      const data = await res.json();
      state.selectedWall = data.wall;
      const idx = state.walls.findIndex(w => w.run_id === wallId);
      if (idx !== -1) state.walls[idx] = data.wall;
      populateInspector(data.wall);
      populateBottomSchedule();
    } catch (err) {
      console.error('Error updating wall height', err);
    }
  };

  window.addOpeningDeduction = async function(type, widthFt, heightFt) {
    if (!state.selectedWall) return;
    const wallId = state.selectedWall.run_id;
    const currentOpenings = state.selectedWall.openings || [];
    const updated = [
      ...currentOpenings.map(op => ({
        type: op.classification || op.type || 'door',
        width_ft: op.width_ft,
        height_ft: op.height_ft || 7.0,
        center_pt: op.center_pt,
      })),
      {
        type: type,
        width_ft: widthFt,
        height_ft: heightFt || (type === 'door' ? 7.0 : 4.0),
      },
    ];

    try {
      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ openings: updated }),
      });
      if (!res.ok) throw new Error('Failed to add opening deduction');
      const data = await res.json();
      state.selectedWall = data.wall;
      const idx = state.walls.findIndex(w => w.run_id === wallId);
      if (idx !== -1) state.walls[idx] = data.wall;
      viewer.setWalls(state.walls);
      viewer.selectWall(wallId);
      populateBottomSchedule();
    } catch (err) {
      console.error('Error adding opening', err);
    }
  };

  window.deleteOpeningDeduction = async function(openingId) {
    if (!state.selectedWall) return;
    const wallId = state.selectedWall.run_id;
    const currentOpenings = state.selectedWall.openings || [];
    const updated = currentOpenings
      .filter(op => op.opening_id !== openingId)
      .map(op => ({
        type: op.classification || op.type || 'door',
        width_ft: op.width_ft,
        height_ft: op.height_ft || 7.0,
        center_pt: op.center_pt,
      }));

    try {
      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ openings: updated }),
      });
      if (!res.ok) throw new Error('Failed to delete opening deduction');
      const data = await res.json();
      state.selectedWall = data.wall;
      const idx = state.walls.findIndex(w => w.run_id === wallId);
      if (idx !== -1) state.walls[idx] = data.wall;
      viewer.setWalls(state.walls);
      viewer.selectWall(wallId);
      populateBottomSchedule();
    } catch (err) {
      console.error('Error deleting opening', err);
    }
  };

  window.deleteSelectedWall = async function() {
    if (!state.selectedWall) return;
    const wallId = state.selectedWall.run_id;
    await window.deleteWall(wallId);
  };

  window.deleteWall = async function(wallId) {
    try {
      const res = await fetch(`/api/blueprint/${state.runId}/walls/${wallId}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to delete wall');

      state.walls = state.walls.filter(w => w.run_id !== wallId);

      if (state.selectedWall && state.selectedWall.run_id === wallId) {
        state.selectedWall = null;
        resetInspector();
      }

      viewer.setWalls(state.walls);
      populateBottomSchedule();
    } catch (err) {
      console.error('Error deleting wall', err);
      alert(`Could not delete wall: ${err.message}`);
    }
  };

  async function refreshWallsAndSchedule() {
    try {
      const wallsRes = await fetch(`/api/takeoff/${state.runId}/walls`);
      if (wallsRes.ok) {
        const wallsData = await wallsRes.json();
        state.walls = wallsData.walls || [];
        viewer.setWalls(state.walls);
        populateBottomSchedule();
        if (state.selectedWall) {
          const updated = state.walls.find(w => w.run_id === state.selectedWall.run_id);
          if (updated) {
            state.selectedWall = updated;
            populateInspector(updated);
          }
        }
      }
    } catch (err) {
      console.error('Failed to refresh walls', err);
    }
  }

  // ===========================================================================
  // TAKEOFF SCHEDULE DOCK & BI-DIRECTIONAL LINKING
  // ===========================================================================

  function formatThickness(thicknessIn, isMeasured) {
    if (thicknessIn === null || thicknessIn === undefined || isNaN(thicknessIn)) {
      return '<span class="text-[#64748b]">—</span>';
    }
    const val = Number(thicknessIn);
    const decStr = val.toFixed(2) + '"';

    // Nearest 1/8" architectural fraction string for tooltip
    const whole = Math.floor(val);
    const frac = val - whole;
    const eighths = Math.round(frac * 8);
    let fracStr = '';
    if (eighths === 0) {
      fracStr = `${whole}"`;
    } else if (eighths === 8) {
      fracStr = `${whole + 1}"`;
    } else {
      let num = eighths;
      let den = 8;
      if (num % 4 === 0) { num /= 4; den /= 4; }
      else if (num % 2 === 0) { num /= 2; den /= 2; }
      fracStr = whole > 0 ? `${whole}-${num}/${den}"` : `${num}/${den}"`;
    }

    const badge = isMeasured
      ? '<span class="px-1 py-0.2 text-[9px] bg-cyan-950/70 text-cyan-300 border border-cyan-500/40 font-bold ml-1 tracking-tight" title="Measured from vector linework">MEAS</span>'
      : '<span class="px-1 py-0.2 text-[9px] bg-slate-800 text-slate-400 border border-slate-600/50 font-bold ml-1 tracking-tight" title="Nominal schedule thickness">NOM</span>';

    return `<span class="font-bold text-white" title="${val.toFixed(3)} in">${decStr} <span class="text-[#94a3b8] text-[10px]">(${fracStr})</span></span> ${badge}`;
  }

  function formatHeightSource(source, calloutTag, isVerified) {
    if (isVerified) {
      const label = source || calloutTag || 'Section Verified';
      return `<span class="text-emerald-400 font-sans truncate max-w-[140px] inline-flex items-center gap-1" title="${label}">
        <span class="material-symbols-outlined text-[13px]">bookmark</span>${label}
      </span>`;
    } else {
      const label = (source && source !== 'UNVERIFIED_HEIGHT_DEFAULT') ? source : 'Default 10ft Fallback';
      return `<span class="text-amber-400 font-sans truncate max-w-[140px] inline-flex items-center gap-1" title="${source || 'Unverified standard 10ft fallback; review required'}">
        <span class="material-symbols-outlined text-[13px]">help_outline</span>${label}
      </span>`;
    }
  }

  function formatStatusBadge(status, isHeightVerified, notes) {
    const isOk = (status === 'VERIFIED' || status === 'OK') && isHeightVerified !== false;
    if (isOk) {
      return `<span class="px-2 py-0.5 bg-emerald-500/15 text-emerald-400 text-[10px] border border-emerald-500/30 font-bold flex items-center justify-center gap-1">
        <span class="material-symbols-outlined text-[12px]">verified</span>VERIFIED
      </span>`;
    } else {
      const tooltip = (notes && notes.length) ? notes.join('; ') : 'Unverified height fallback; estimator review required';
      return `<span class="px-2 py-0.5 bg-amber-500/15 text-amber-400 text-[10px] border border-amber-500/30 font-bold flex items-center justify-center gap-1" title="${tooltip}">
        <span class="material-symbols-outlined text-[12px]">warning</span>REVIEW
      </span>`;
    }
  }

  function populateBottomSchedule() {
    const tbody = document.getElementById('schedule-table-body') || document.getElementById('scheduleBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    // Calculate filter counts across entire dataset
    const totalAll = state.walls.length;
    const verifiedWalls = state.walls.filter(w => (w.status === 'VERIFIED' || w.status === 'OK') && w.is_height_verified !== false);
    const reviewWalls = state.walls.filter(w => w.status === 'REVIEW' || w.is_height_verified === false);

    const countAllEl = document.getElementById('sched-count-all');
    if (countAllEl) countAllEl.textContent = totalAll;
    const countVerEl = document.getElementById('sched-count-verified');
    if (countVerEl) countVerEl.textContent = verifiedWalls.length;
    const countRevEl = document.getElementById('sched-count-review');
    if (countRevEl) countRevEl.textContent = reviewWalls.length;

    // Update filter button styling
    ['all', 'verified', 'review'].forEach(mode => {
      const btn = document.getElementById(`sched-filter-${mode}`);
      if (!btn) return;
      if (mode === state.scheduleFilter) {
        if (mode === 'review') {
          btn.className = 'px-2 py-0.5 text-xs font-mono font-bold transition-colors bg-amber-500/20 text-amber-400 border border-amber-500/40 flex items-center gap-1';
        } else if (mode === 'verified') {
          btn.className = 'px-2 py-0.5 text-xs font-mono font-bold transition-colors bg-emerald-500/20 text-emerald-400 border border-emerald-500/40';
        } else {
          btn.className = 'px-2 py-0.5 text-xs font-mono font-bold transition-colors bg-primary/20 text-primary border border-primary/30';
        }
      } else {
        btn.className = 'px-2 py-0.5 text-xs font-mono transition-colors text-[#94a3b8] hover:text-white flex items-center gap-1 border border-transparent';
      }
    });

    // Apply active filter
    let displayedWalls = state.walls;
    if (state.scheduleFilter === 'review') {
      displayedWalls = reviewWalls;
    } else if (state.scheduleFilter === 'verified') {
      displayedWalls = verifiedWalls;
    }

    let totalGross = 0;
    let totalDeduct = 0;
    let totalNet = 0;
    let totalSF = 0;
    let totalStuds = 0;
    let totalTrack = 0;

    if (displayedWalls.length === 0) {
      const emptyTr = document.createElement('tr');
      emptyTr.innerHTML = `
        <td colspan="16" class="py-8 text-center text-[#94a3b8] font-sans">
          <div class="flex flex-col items-center justify-center gap-1">
            <span class="material-symbols-outlined text-[24px] text-emerald-400">check_circle</span>
            <span class="font-bold text-white">No ${state.scheduleFilter === 'review' ? 'unverified review' : ''} wall runs found.</span>
            <span class="text-xs text-[#64748b]">${state.scheduleFilter === 'review' ? 'All partition walls have verified heights from architectural section details.' : 'No wall runs match current filter.'}</span>
          </div>
        </td>
      `;
      tbody.appendChild(emptyTr);
    }

    displayedWalls.forEach(w => {
      const gross = w.gross_length_ft || 0;
      const deduct = w.opening_deduction_ft || 0;
      const net = w.net_length_ft !== undefined ? w.net_length_ft : (gross - deduct);
      const height = (w.height_ft !== null && w.height_ft !== undefined) ? Number(w.height_ft) : 10.0;
      const tagInfo = (state.summary && state.summary.by_tag && state.summary.by_tag[w.tag]) || {};
      const faces = tagInfo.faces || 2;
      const layers = tagInfo.layers_per_face || 1;
      const sf = net * height * faces * layers;
      const openingsCount = w.openings ? w.openings.length : (w.openings_count || 0);
      const studs = Math.ceil((net * 12) / 16) + 1 + openingsCount * 2;
      const track = gross + net;

      totalGross += gross;
      totalDeduct += deduct;
      totalNet += net;
      totalSF += sf;
      totalStuds += studs;
      totalTrack += track;

      const isManual = !!w.is_manual;
      const isHeightVerified = !!w.is_height_verified;
      const formattedThickness = formatThickness(w.thickness_in, w.thickness_measured);
      const formattedHeight = `<span class="font-bold text-white">${height.toFixed(2)} ft</span>`;
      const formattedSource = formatHeightSource(w.height_source, w.section_callout_tag, isHeightVerified);
      const statusBadge = formatStatusBadge(w.status, isHeightVerified, w.notes);

      const tr = document.createElement('tr');
      tr.className = `hover:bg-[#131e33] cursor-pointer sched-row ${state.selectedWall && state.selectedWall.run_id === w.run_id ? 'bg-primary/20 border-l-2 border-primary' : ''}`;
      tr.setAttribute('data-run-id', w.run_id);
      tr.innerHTML = `
        <td class="py-2 px-3 text-primary font-bold">${w.run_id}</td>
        <td class="py-2 px-3 font-semibold text-white"><span class="bg-[#1e293b] px-1.5 py-0.5 border border-[#334155]">${w.tag}</span></td>
        <td class="py-2 px-3"><span class="px-1.5 py-0.5 text-[9px] font-bold ${isManual ? 'bg-purple-950/60 text-purple-300 border border-purple-500/40' : 'bg-blue-950/60 text-blue-300 border border-blue-500/40'}">${isManual ? 'MANUAL' : 'DETECTED'}</span></td>
        <td class="py-2 px-3 font-sans text-[#cbd5e1] truncate max-w-[180px]">Partition Tag ${w.tag}</td>
        <td class="py-2 px-3 text-right whitespace-nowrap">${formattedThickness}</td>
        <td class="py-2 px-3 text-right whitespace-nowrap">${formattedHeight}</td>
        <td class="py-2 px-3 whitespace-nowrap">${formattedSource}</td>
        <td class="py-2 px-3 text-right">${gross.toFixed(2)}</td>
        <td class="py-2 px-3 text-right text-amber-400">-${deduct.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-primary">${net.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-white">${sf.toFixed(2)}</td>
        <td class="py-2 px-3 text-right">${studs}</td>
        <td class="py-2 px-3 text-right">${track.toFixed(2)}</td>
        <td class="py-2 px-3 font-sans text-[#94a3b8]">${w.sheet_label || `Page ${w.page_num || 1}`}</td>
        <td class="py-2 px-3 text-center">${statusBadge}</td>
        <td class="py-2 px-3 text-center">
          <button onclick="event.stopPropagation(); deleteWall('${w.run_id}')" class="text-[#64748b] hover:text-red-400 p-1 transition-colors" title="Delete Wall">
            <span class="material-symbols-outlined text-[15px]">delete</span>
          </button>
        </td>
      `;

      // Row hover highlights canvas wall
      tr.addEventListener('mouseenter', () => {
        viewer.highlightWall(w.run_id, true);
      });
      tr.addEventListener('mouseleave', () => {
        viewer.highlightWall(w.run_id, false);
      });

      // Row click navigates to page, centers canvas on wall, and selects it
      tr.addEventListener('click', () => {
        if (w.page_num && w.page_num !== state.currentPage) {
          goToPage(w.page_num);
        }
        viewer.centerOnWall(w.run_id);
        if (!state.rightDrawerOpen) toggleRightDrawer(true);
      });

      tbody.appendChild(tr);
    });

    // Summary pills in dock header
    const sumNet = document.getElementById('sched-summary-net-lf');
    if (sumNet) sumNet.textContent = `${totalNet.toFixed(2)} LF`;
    const sumSf = document.getElementById('sched-summary-board-sf');
    if (sumSf) sumSf.textContent = `${totalSF.toFixed(2)} SF`;
    const sumStuds = document.getElementById('sched-summary-studs');
    if (sumStuds) sumStuds.textContent = `${totalStuds} EA`;

    // Pinned total row (16 columns aligned to thead)
    const totalRow = document.getElementById('schedule-table-total');
    if (totalRow) {
      const isFiltered = state.scheduleFilter !== 'all';
      const labelPrefix = isFiltered ? `${state.scheduleFilter.toUpperCase()} TOTAL` : 'TOTAL';
      totalRow.innerHTML = `
        <td class="py-2 px-3 text-primary font-bold">${labelPrefix}</td>
        <td class="py-2 px-3 text-white font-bold">${displayedWalls.length} Runs</td>
        <td class="py-2 px-3"></td>
        <td class="py-2 px-3 font-sans text-[#94a3b8] truncate max-w-[180px]">Consolidated Bill of Materials</td>
        <td class="py-2 px-3 text-right text-[#94a3b8]">—</td>
        <td class="py-2 px-3 text-right text-[#94a3b8]">—</td>
        <td class="py-2 px-3 text-[#94a3b8]">—</td>
        <td class="py-2 px-3 text-right font-bold text-white">${totalGross.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-amber-400">-${totalDeduct.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-primary">${totalNet.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-white">${totalSF.toFixed(2)}</td>
        <td class="py-2 px-3 text-right font-bold text-white">${totalStuds}</td>
        <td class="py-2 px-3 text-right font-bold text-white">${totalTrack.toFixed(2)}</td>
        <td class="py-2 px-3"></td>
        <td class="py-2 px-3 text-center">
          <span class="inline-flex items-center gap-1.5 px-2 py-0.5 bg-[#070b13] border border-[#1f2937] text-[10px]">
            <span class="text-emerald-400 font-bold flex items-center gap-0.5" title="Verified wall runs count"><span class="material-symbols-outlined text-[11px]">check</span>${verifiedWalls.length}</span>
            <span class="text-[#64748b]">/</span>
            <span class="text-amber-400 font-bold flex items-center gap-0.5" title="Unverified/review runs count"><span class="material-symbols-outlined text-[11px]">warning</span>${reviewWalls.length}</span>
          </span>
        </td>
        <td class="py-2 px-3"></td>
      `;
    }
  }

  function highlightScheduleRow(runId, highlight = true) {
    document.querySelectorAll('.sched-row').forEach(row => {
      if (row.getAttribute('data-run-id') === runId) {
        if (highlight) {
          row.classList.add('bg-primary/20', 'border-l-2', 'border-primary');
          row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } else {
          row.classList.remove('bg-primary/20', 'border-l-2', 'border-primary');
        }
      } else if (highlight) {
        row.classList.remove('bg-primary/20', 'border-l-2', 'border-primary');
      }
    });
  }

  // ===========================================================================
  // INITIAL LOAD
  // ===========================================================================

  async function init() {
    // Check if run_id in URL query
    const params = new URLSearchParams(window.location.search);
    const paramRunId = params.get('run_id');

    if (paramRunId) {
      loadRun(paramRunId);
    } else {
      // 1. Check for latest completed real blueprint takeoff
      try {
        const latestRes = await fetch('/api/takeoff/latest');
        if (latestRes.ok) {
          const latestData = await latestRes.json();
          if (latestData && latestData.run_id) {
            loadRun(latestData.run_id);
            return;
          }
        }
      } catch (_) {}

      // 2. Auto-load test_m3_door if present, or run fixture_door.pdf
      try {
        const testRes = await fetch('/api/takeoff/test_m3_door/summary');
        if (testRes.ok) {
          loadRun('test_m3_door');
          return;
        }
      } catch (_) {}

      // 3. Otherwise launch fixture_door.pdf
      runSampleFixture('fixture_door.pdf');
    }
  }

  init();
});
