/**
 * viewer.js: High-Density Interactive CAD Canvas Viewer & Vector Overlay.
 *
 * Implements Milestone 4 capabilities:
 * - High-res raster page image loading from /api/blueprint/{run_id}/page/{page_num}/image
 * - Interactive pan & zoom with mouse dragging, wheel zoom, and micro-toolbar controls
 * - Vector SVG overlay rendering dual-red traced drywall wall spines, opening gaps, and tag labels
 * - 2-Point Scale Calibration tool with live dashed rubberband and distance modal
 * - Manual Wall Ruler / Drawing tool with dual-red live preview and dynamic LF display
 * - Draggable circular vertex endpoint handles on selected walls with live coordinate updates
 * - Bi-directional hover & selection linking between Canvas, Inspector, and Takeoff Schedule Dock
 */

class CADCanvasViewer {
  constructor(options = {}) {
    this.container = document.getElementById(options.containerId || 'canvas-viewport');
    this.transformLayer = document.getElementById(options.transformLayerId || 'canvas-transform-layer');
    this.imgElement = document.getElementById(options.imageId || 'sheet-image');
    this.svgOverlay = document.getElementById(options.svgId || 'svg-overlay');
    this.zoomLabel = document.getElementById(options.zoomLabelId || 'zoom-level-label');

    // Callback hooks
    this.onWallSelected = options.onWallSelected || (() => {});
    this.onPanZoomChanged = options.onPanZoomChanged || (() => {});
    this.onCalibrationComplete = options.onCalibrationComplete || (() => {});
    this.onWallCreated = options.onWallCreated || (() => {});
    this.onWallEndpointsChanged = options.onWallEndpointsChanged || (() => {});
    this.onWallHover = options.onWallHover || (() => {});

    // Pan & Zoom state
    this.scale = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.isDragging = false;
    this.startX = 0;
    this.startY = 0;
    this.activeTool = 'select'; // 'select' | 'pan' | 'calibrate' | 'wall' | 'wall_ruler'

    // Document & Sheet metadata
    this.currentRunId = null;
    this.currentPageNum = 1;
    this.currentMode = 'overlay';
    this.pdfPageWidth = 1000;
    this.pdfPageHeight = 800;
    this.imgWidth = 0;
    this.imgHeight = 0;
    this.ptToPxRatio = 1.0;
    this.currentScaleFtPerPt = 0.111111;

    // Data elements
    this.walls = [];
    this.selectedWallId = null;
    this.visibleLayers = {
      'A-WALL': true,
      'S-COLS': true,
      'A-DIMS': true,
      'A-AREA': true,
      'M-ROOF': true,
      'G-ANNO': true,
      'GAP DETECT': true,
    };

    // Interactive drawing & handle states
    this.calibPt1 = null;
    this.isCalibrating = false;
    this.wallStartPt = null;
    this.isDrawingWall = false;
    this.dragHandle = null; // { wall, handleIdx, spine, group, band, spineLine, tagBadge, tagLabel }

    this._initEvents();
  }

  _initEvents() {
    // Canvas mousedown
    this.container.addEventListener('mousedown', (e) => {
      // Panning tool or middle mouse or shift key
      if (this.activeTool === 'pan' || e.button === 1 || e.shiftKey) {
        this.isDragging = true;
        this.startX = e.clientX - this.panX;
        this.startY = e.clientY - this.panY;
        this.container.style.cursor = 'grabbing';
        e.preventDefault();
        return;
      }

      if (e.button !== 0) return; // Only primary button for drawing tools

      const pt = this.clientToPoint(e.clientX, e.clientY);

      // Calibration Tool mode
      if (this.activeTool === 'calibrate') {
        if (!this.isCalibrating) {
          this.isCalibrating = true;
          this.calibPt1 = pt;
          this._renderCalibrationStart(pt);
        } else {
          this.isCalibrating = false;
          const pt1 = this.calibPt1;
          const pt2 = pt;
          const distPt = Math.hypot(pt2.x - pt1.x, pt2.y - pt1.y);
          const distPx = Math.hypot(pt2.pxX - pt1.pxX, pt2.pxY - pt1.pxY);
          this._clearDrawingPreviews();
          this.calibPt1 = null;
          this.onCalibrationComplete({ pt1, pt2, distPt, distPx });
        }
        e.preventDefault();
        return;
      }

      // Manual Wall Drawing / Ruler Tool mode
      if (this.activeTool === 'wall' || this.activeTool === 'wall_ruler') {
        if (!this.isDrawingWall) {
          this.isDrawingWall = true;
          this.wallStartPt = pt;
          this._renderWallStart(pt);
        } else {
          this.isDrawingWall = false;
          const start = this.wallStartPt;
          const end = pt;
          const distPt = Math.hypot(end.x - start.x, end.y - start.y);
          this._clearDrawingPreviews();
          this.wallStartPt = null;
          if (distPt > 2.0) {
            this.onWallCreated({ start, end });
          }
        }
        e.preventDefault();
        return;
      }

      // Select mode background click: if clicking canvas directly, deselect
      if (this.activeTool === 'select' && (e.target === this.container || e.target === this.svgOverlay || e.target === this.imgElement)) {
        this.deselectWall();
      }
    });

    // Window mousemove
    window.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        this.panX = e.clientX - this.startX;
        this.panY = e.clientY - this.startY;
        this._updateTransform();
        return;
      }

      if (this.dragHandle) {
        const curr = this.clientToPoint(e.clientX, e.clientY);
        this._updateHandleDragLive(curr);
        return;
      }

      if (this.isCalibrating && this.calibPt1) {
        const curr = this.clientToPoint(e.clientX, e.clientY);
        this._renderCalibrationRubberband(this.calibPt1, curr);
        return;
      }

      if (this.isDrawingWall && this.wallStartPt) {
        const curr = this.clientToPoint(e.clientX, e.clientY);
        this._renderWallRubberband(this.wallStartPt, curr);
        return;
      }
    });

    // Window mouseup
    window.addEventListener('mouseup', () => {
      if (this.isDragging) {
        this.isDragging = false;
        this.container.style.cursor = this.activeTool === 'pan' ? 'grab' : (this.activeTool === 'select' ? 'default' : 'crosshair');
      }

      if (this.dragHandle) {
        this._finishHandleDrag();
      }
    });

    // Mouse wheel zoom
    this.container.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = this.container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
      const newScale = Math.min(Math.max(this.scale * zoomFactor, 0.2), 6.0);

      this.panX = mouseX - (mouseX - this.panX) * (newScale / this.scale);
      this.panY = mouseY - (mouseY - this.panY) * (newScale / this.scale);
      this.scale = newScale;

      this._updateTransform();
    }, { passive: false });
  }

  /**
   * Transforms screen client coordinates to blueprint points and SVG overlay pixels.
   */
  clientToPoint(clientX, clientY) {
    const cRect = this.container.getBoundingClientRect();
    const pxX = (clientX - cRect.left - this.panX) / this.scale;
    const pxY = (clientY - cRect.top - this.panY) / this.scale;
    const ratio = this.ptToPxRatio > 0 ? this.ptToPxRatio : 1.0;
    const ptX = pxX / ratio;
    const ptY = pxY / ratio;
    return { x: ptX, y: ptY, pxX, pxY };
  }

  setTool(tool) {
    this.activeTool = tool;
    this._clearDrawingPreviews();
    this.isCalibrating = false;
    this.isDrawingWall = false;
    this.calibPt1 = null;
    this.wallStartPt = null;

    if (tool === 'pan') {
      this.container.style.cursor = 'grab';
    } else if (tool === 'calibrate' || tool === 'wall' || tool === 'wall_ruler') {
      this.container.style.cursor = 'crosshair';
    } else {
      this.container.style.cursor = 'default';
    }
  }

  zoomIn() {
    this.scale = Math.min(this.scale * 1.25, 6.0);
    this._updateTransform();
  }

  zoomOut() {
    this.scale = Math.max(this.scale * 0.8, 0.2);
    this._updateTransform();
  }

  fitToScreen() {
    if (!this.imgWidth || !this.imgHeight) return;
    const containerWidth = this.container.clientWidth || 1000;
    const containerHeight = this.container.clientHeight || 700;

    const scaleX = (containerWidth - 60) / this.imgWidth;
    const scaleY = (containerHeight - 60) / this.imgHeight;
    this.scale = Math.min(scaleX, scaleY, 1.5);

    this.panX = (containerWidth - this.imgWidth * this.scale) / 2;
    this.panY = (containerHeight - this.imgHeight * this.scale) / 2;

    this._updateTransform();
  }

  resetView() {
    this.scale = 1.0;
    this.panX = 30;
    this.panY = 30;
    this._updateTransform();
  }

  _updateTransform() {
    this.transformLayer.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.scale})`;
    if (this.zoomLabel) {
      this.zoomLabel.textContent = `${Math.round(this.scale * 100)}%`;
    }
    this.onPanZoomChanged(this.scale, this.panX, this.panY);
  }

  /**
   * Loads a blueprint page image and initializes vector overlay.
   */
  async loadPage(runId, pageNum, mode = 'overlay', sheetInfo = null) {
    this.currentRunId = runId;
    this.currentPageNum = pageNum;
    this.currentMode = mode;

    if (sheetInfo) {
      this.pdfPageWidth = sheetInfo.width || 1000;
      this.pdfPageHeight = sheetInfo.height || 800;
      if (sheetInfo.ft_per_pt) {
        this.currentScaleFtPerPt = sheetInfo.ft_per_pt;
      }
    }

    const imgUrl = `/api/blueprint/${runId}/page/${pageNum}/image?mode=${mode}&dpi=150`;

    return new Promise((resolve, reject) => {
      this.imgElement.onload = () => {
        this.imgWidth = this.imgElement.naturalWidth;
        this.imgHeight = this.imgElement.naturalHeight;

        this.svgOverlay.setAttribute('width', this.imgWidth);
        this.svgOverlay.setAttribute('height', this.imgHeight);
        this.svgOverlay.setAttribute('viewBox', `0 0 ${this.imgWidth} ${this.imgHeight}`);

        this.ptToPxRatio = this.imgWidth / (this.pdfPageWidth || 1000);

        this.fitToScreen();
        this.renderWallVectors();
        resolve();
      };

      this.imgElement.onerror = (err) => {
        console.error('Failed to load blueprint page image', err);
        reject(err);
      };

      this.imgElement.src = imgUrl;
    });
  }

  setWalls(walls) {
    this.walls = walls || [];
    this.renderWallVectors();
  }

  setLayerVisibility(layerName, visible) {
    this.visibleLayers[layerName] = !!visible;
    this.renderWallVectors();
  }

  // ===========================================================================
  // VECTOR OVERLAYS & DUAL-RED VISUAL ANNOTATIONS
  // ===========================================================================

  /**
   * Renders interactive dual-red vector overlays for wall runs.
   * Highlight band: rgba(239, 68, 68, 0.38) at 16px
   * Centerline spine: #dc2626 at 2.5px
   * Selected: cyan highlight band + pure white spine (#ffffff, 3.5px) + draggable endpoint handles
   */
  renderWallVectors() {
    while (this.svgOverlay.firstChild) {
      this.svgOverlay.removeChild(this.svgOverlay.firstChild);
    }

    if (!this.visibleLayers['A-WALL']) {
      return;
    }

    const pageRuns = this.walls.filter(w => (w.page_num || 1) === this.currentPageNum);

    pageRuns.forEach((wall) => {
      const spine = wall.spine;
      if (!spine) return;

      const x1 = spine.x1 * this.ptToPxRatio;
      const y1 = spine.y1 * this.ptToPxRatio;
      const x2 = spine.x2 * this.ptToPxRatio;
      const y2 = spine.y2 * this.ptToPxRatio;
      const isSelected = this.selectedWallId === wall.run_id;

      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.setAttribute('data-wall-id', wall.run_id);
      group.setAttribute('class', `wall-vector-group ${isSelected ? 'selected' : ''}`);

      // 1. Highlight Band (translucent clickable stroke)
      const thickPx = (wall.thickness_pt || 0) * this.ptToPxRatio;
      const bandStroke = Math.max(16 * this.ptToPxRatio, thickPx, 14);
      const band = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      band.setAttribute('x1', x1);
      band.setAttribute('y1', y1);
      band.setAttribute('x2', x2);
      band.setAttribute('y2', y2);
      band.setAttribute('stroke-width', bandStroke);
      band.setAttribute('class', `wall-highlight-band ${isSelected ? 'selected' : ''}`);

      // 2. Centerline Spine
      const spineLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      spineLine.setAttribute('x1', x1);
      spineLine.setAttribute('y1', y1);
      spineLine.setAttribute('x2', x2);
      spineLine.setAttribute('y2', y2);
      spineLine.setAttribute('stroke-width', Math.max(2.5 * this.ptToPxRatio, 2));
      spineLine.setAttribute('class', `wall-spine-edge ${isSelected ? 'selected' : ''}`);

      // 3. Opening Deductions (Gaps)
      if (wall.openings && wall.openings.length > 0) {
        wall.openings.forEach((op) => {
          if (op.center_pt) {
            const opX = op.center_pt.x * this.ptToPxRatio;
            const opY = op.center_pt.y * this.ptToPxRatio;
            const opRadius = (op.width_pt ? op.width_pt / 2 : 14) * this.ptToPxRatio;

            const opCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            opCircle.setAttribute('cx', opX);
            opCircle.setAttribute('cy', opY);
            opCircle.setAttribute('r', opRadius);
            opCircle.setAttribute('fill', 'rgba(245, 158, 11, 0.25)');
            opCircle.setAttribute('stroke', '#f59e0b');
            opCircle.setAttribute('stroke-width', '1.5');
            opCircle.setAttribute('stroke-dasharray', '3 2');
            group.appendChild(opCircle);
          }
        });
      }

      // 4. Tag Badge at Midpoint
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      const tagText = wall.tag || 'DRW';
      const badgeWidth = Math.max(tagText.length * 9 + 14, 34);
      const badgeHeight = 18;

      const badgeRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      badgeRect.setAttribute('x', midX - badgeWidth / 2);
      badgeRect.setAttribute('y', midY - badgeHeight / 2);
      badgeRect.setAttribute('width', badgeWidth);
      badgeRect.setAttribute('height', badgeHeight);
      badgeRect.setAttribute('rx', '0');
      badgeRect.setAttribute('class', `wall-tag-badge ${isSelected ? 'selected' : ''}`);

      const textNode = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      textNode.setAttribute('x', midX);
      textNode.setAttribute('y', midY);
      textNode.setAttribute('font-size', '10px');
      textNode.setAttribute('class', 'wall-tag-label');
      textNode.textContent = tagText;

      // Selection click handler
      const selectHandler = (e) => {
        e.stopPropagation();
        this.selectWall(wall.run_id);
      };

      band.addEventListener('click', selectHandler);
      badgeRect.addEventListener('click', selectHandler);
      textNode.addEventListener('click', selectHandler);

      // Bi-directional hover handlers with Instant CAD HUD Popover
      group.addEventListener('mouseenter', (e) => {
        this.onWallHover(wall.run_id, true);
        this._showHoverHUD(wall, e);
      });
      group.addEventListener('mousemove', (e) => {
        this._moveHoverHUD(e);
      });
      group.addEventListener('mouseleave', () => {
        this.onWallHover(wall.run_id, false);
        this._hideHoverHUD();
      });

      // Hover Tooltip via SVG <title>
      const tooltip = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      const isHVer = !!wall.is_height_verified;
      let tooltipText = `DRYWALL PARTITION: Tag ${wall.tag || 'DRW'} [${wall.run_id}]\n` +
        `Gross: ${(wall.gross_length_ft || 0).toFixed(2)} LF | Deduct: -${(wall.opening_deduction_ft || 0).toFixed(2)} LF | Net: ${(wall.net_length_ft || 0).toFixed(2)} LF\n`;

      if (wall.thickness_in !== undefined && wall.thickness_in !== null) {
        tooltipText += `Thickness: ${Number(wall.thickness_in).toFixed(2)}" (${wall.thickness_measured ? 'CAD Measured' : 'Schedule Nominal'})\n`;
      }
      if (wall.height_ft !== undefined && wall.height_ft !== null) {
        const secTag = wall.section_callout_tag ? ` [Section: ${wall.section_callout_tag}]` : '';
        tooltipText += `Height: ${Number(wall.height_ft).toFixed(1)} ft (${isHVer ? 'VERIFIED' : 'REVIEW REQUIRED'}${secTag})\n`;
        tooltipText += `Height Source: ${wall.height_source || (isHVer ? 'Section Detail' : 'UNVERIFIED_HEIGHT_DEFAULT')}\n`;
      }
      if (!isHVer && !wall.is_manual) {
        tooltipText += `Review Note: No explicit height found on referenced detail; defaulted to 10.0 ft.\n`;
      }
      tooltipText += `Status: ${wall.status || (isHVer ? 'VERIFIED' : 'REVIEW')}`;
      if (wall.material_layers && Array.isArray(wall.material_layers) && wall.material_layers.length > 0) {
        const layerStr = wall.material_layers.map(l => `${l.side || ''}: ${l.material || ''}`).join(' | ');
        tooltipText += `\nLayers: ${layerStr}`;
      }
      tooltip.textContent = tooltipText;

      group.appendChild(tooltip);
      group.appendChild(band);
      group.appendChild(spineLine);
      group.appendChild(badgeRect);
      group.appendChild(textNode);

      // 5. Draggable Endpoint Handles (when selected)
      if (isSelected) {
        const handle1 = this._createEndpointHandle(wall, 1, x1, y1);
        const handle2 = this._createEndpointHandle(wall, 2, x2, y2);
        group.appendChild(handle1);
        group.appendChild(handle2);
      }

      this.svgOverlay.appendChild(group);
    });

    // Ensure live preview layer stays on top
    this._ensurePreviewLayer();
  }

  // ===========================================================================
  // DRAGGABLE VERTEX HANDLES
  // ===========================================================================

  _createEndpointHandle(wall, handleIdx, pxX, pxY) {
    const handle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    handle.setAttribute('cx', pxX);
    handle.setAttribute('cy', pxY);
    handle.setAttribute('r', '6');
    handle.setAttribute('class', 'wall-endpoint-handle');
    handle.setAttribute('data-handle-idx', handleIdx);
    handle.setAttribute('data-wall-id', wall.run_id);
    handle.setAttribute('title', `Drag Endpoint ${handleIdx}`);

    handle.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      e.preventDefault();
      this._startHandleDrag(wall, handleIdx, e);
    });

    return handle;
  }

  _startHandleDrag(wall, handleIdx, e) {
    const group = this.svgOverlay.querySelector(`.wall-vector-group[data-wall-id="${wall.run_id}"]`);
    const band = group ? group.querySelector('.wall-highlight-band') : null;
    const spineLine = group ? group.querySelector('.wall-spine-edge') : null;
    const tagBadge = group ? group.querySelector('.wall-tag-badge') : null;
    const tagLabel = group ? group.querySelector('.wall-tag-label') : null;
    const handle = group ? group.querySelector(`.wall-endpoint-handle[data-handle-idx="${handleIdx}"]`) : null;

    this.dragHandle = {
      wall,
      handleIdx,
      spine: { ...wall.spine },
      group,
      band,
      spineLine,
      tagBadge,
      tagLabel,
      handle,
    };

    this.container.style.cursor = 'move';
  }

  _updateHandleDragLive(currPt) {
    if (!this.dragHandle) return;
    const { wall, handleIdx, band, spineLine, tagBadge, tagLabel, handle } = this.dragHandle;

    if (handleIdx === 1) {
      wall.spine.x1 = currPt.x;
      wall.spine.y1 = currPt.y;
    } else {
      wall.spine.x2 = currPt.x;
      wall.spine.y2 = currPt.y;
    }

    const x1 = wall.spine.x1 * this.ptToPxRatio;
    const y1 = wall.spine.y1 * this.ptToPxRatio;
    const x2 = wall.spine.x2 * this.ptToPxRatio;
    const y2 = wall.spine.y2 * this.ptToPxRatio;

    if (band) {
      band.setAttribute('x1', x1);
      band.setAttribute('y1', y1);
      band.setAttribute('x2', x2);
      band.setAttribute('y2', y2);
    }

    if (spineLine) {
      spineLine.setAttribute('x1', x1);
      spineLine.setAttribute('y1', y1);
      spineLine.setAttribute('x2', x2);
      spineLine.setAttribute('y2', y2);
    }

    if (handle) {
      handle.setAttribute('cx', handleIdx === 1 ? x1 : x2);
      handle.setAttribute('cy', handleIdx === 1 ? y1 : y2);
    }

    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    if (tagBadge) {
      const width = parseFloat(tagBadge.getAttribute('width') || '34');
      const height = parseFloat(tagBadge.getAttribute('height') || '18');
      tagBadge.setAttribute('x', midX - width / 2);
      tagBadge.setAttribute('y', midY - height / 2);
    }
    if (tagLabel) {
      tagLabel.setAttribute('x', midX);
      tagLabel.setAttribute('y', midY);
    }

    // Live length recalculation for inspector
    const dx = wall.spine.x2 - wall.spine.x1;
    const dy = wall.spine.y2 - wall.spine.y1;
    const lenPt = Math.hypot(dx, dy);
    wall.spine.length = lenPt;
    wall.spine.angle = Math.round(Math.atan2(dy, dx) * 180 / Math.PI * 10) / 10;
    wall.gross_length_pt = lenPt;
    const ftPt = wall.ft_per_pt || this.currentScaleFtPerPt || 0.111111;
    wall.gross_length_ft = parseFloat((lenPt * ftPt).toFixed(2));
    wall.net_length_ft = Math.max(0, parseFloat((wall.gross_length_ft - (wall.opening_deduction_ft || 0)).toFixed(2)));

    this.onWallSelected(wall);
  }

  _finishHandleDrag() {
    if (!this.dragHandle) return;
    const { wall } = this.dragHandle;
    this.dragHandle = null;
    this.container.style.cursor = this.activeTool === 'select' ? 'default' : 'crosshair';

    const newStart = { x: wall.spine.x1, y: wall.spine.y1 };
    const newEnd = { x: wall.spine.x2, y: wall.spine.y2 };
    this.onWallEndpointsChanged(wall.run_id, newStart, newEnd);
  }

  // ===========================================================================
  // SELECTION & HIGHLIGHTING
  // ===========================================================================

  selectWall(wallId) {
    this.selectedWallId = wallId;
    const selectedWall = this.walls.find(w => w.run_id === wallId);

    // Re-render wall vectors so draggable handles appear on the selected wall
    this.renderWallVectors();

    if (selectedWall) {
      this.onWallSelected(selectedWall);
    }
  }

  deselectWall() {
    this.selectedWallId = null;
    this.renderWallVectors();
    this.onWallSelected(null);
  }

  highlightWall(wallId, highlight) {
    const group = this.svgOverlay.querySelector(`.wall-vector-group[data-wall-id="${wallId}"]`);
    if (group) {
      if (highlight) {
        group.classList.add('glow-highlight');
      } else {
        group.classList.remove('glow-highlight');
      }
    }
  }

  centerOnWall(wallId) {
    const wall = this.walls.find(w => w.run_id === wallId);
    if (!wall || !wall.spine) return;

    const spine = wall.spine;
    const midX = ((spine.x1 + spine.x2) / 2) * this.ptToPxRatio;
    const midY = ((spine.y1 + spine.y2) / 2) * this.ptToPxRatio;

    const containerWidth = this.container.clientWidth;
    const containerHeight = this.container.clientHeight;

    this.scale = Math.max(this.scale, 1.2);
    this.panX = containerWidth / 2 - midX * this.scale;
    this.panY = containerHeight / 2 - midY * this.scale;

    this._updateTransform();
    this.selectWall(wallId);
  }

  // ===========================================================================
  // LIVE RUBBERBAND DRAWING PREVIEWS
  // ===========================================================================

  _ensurePreviewLayer() {
    let previewGroup = this.svgOverlay.querySelector('#svg-preview-layer');
    if (!previewGroup) {
      previewGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      previewGroup.setAttribute('id', 'svg-preview-layer');
      this.svgOverlay.appendChild(previewGroup);
    }
    return previewGroup;
  }

  _clearDrawingPreviews() {
    const previewGroup = this.svgOverlay.querySelector('#svg-preview-layer');
    if (previewGroup) {
      while (previewGroup.firstChild) {
        previewGroup.removeChild(previewGroup.firstChild);
      }
    }
  }

  _renderCalibrationStart(pt) {
    const group = this._ensurePreviewLayer();
    while (group.firstChild) group.removeChild(group.firstChild);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', pt.pxX);
    circle.setAttribute('cy', pt.pxY);
    circle.setAttribute('r', '7');
    circle.setAttribute('class', 'calibration-point');
    group.appendChild(circle);
  }

  _renderCalibrationRubberband(pt1, pt2) {
    const group = this._ensurePreviewLayer();
    while (group.firstChild) group.removeChild(group.firstChild);

    const distPt = Math.hypot(pt2.x - pt1.x, pt2.y - pt1.y);
    const distPx = Math.hypot(pt2.pxX - pt1.pxX, pt2.pxY - pt1.pxY);

    // Start point
    const startCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    startCircle.setAttribute('cx', pt1.pxX);
    startCircle.setAttribute('cy', pt1.pxY);
    startCircle.setAttribute('r', '6');
    startCircle.setAttribute('class', 'calibration-point');

    // Dashed line
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', pt1.pxX);
    line.setAttribute('y1', pt1.pxY);
    line.setAttribute('x2', pt2.pxX);
    line.setAttribute('y2', pt2.pxY);
    line.setAttribute('class', 'rubberband-line');

    // End point
    const endCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    endCircle.setAttribute('cx', pt2.pxX);
    endCircle.setAttribute('cy', pt2.pxY);
    endCircle.setAttribute('r', '6');
    endCircle.setAttribute('class', 'calibration-point');

    // Distance Badge
    const midX = (pt1.pxX + pt2.pxX) / 2;
    const midY = (pt1.pxX + pt2.pxX) / 2;
    const badgeText = `${distPt.toFixed(1)} pt (${distPx.toFixed(0)} px)`;

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', (pt1.pxX + pt2.pxX) / 2);
    text.setAttribute('y', (pt1.pxY + pt2.pxY) / 2 - 10);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', '#4cd7f6');
    text.setAttribute('font-size', '11px');
    text.setAttribute('font-family', 'JetBrains Mono, monospace');
    text.setAttribute('font-weight', 'bold');
    text.textContent = badgeText;

    group.appendChild(startCircle);
    group.appendChild(line);
    group.appendChild(endCircle);
    group.appendChild(text);
  }

  _renderWallStart(pt) {
    const group = this._ensurePreviewLayer();
    while (group.firstChild) group.removeChild(group.firstChild);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', pt.pxX);
    circle.setAttribute('cy', pt.pxY);
    circle.setAttribute('r', '6');
    circle.setAttribute('fill', '#ef4444');
    circle.setAttribute('stroke', '#ffffff');
    circle.setAttribute('stroke-width', '2');
    group.appendChild(circle);
  }

  _renderWallRubberband(pt1, pt2) {
    const group = this._ensurePreviewLayer();
    while (group.firstChild) group.removeChild(group.firstChild);

    const distPt = Math.hypot(pt2.x - pt1.x, pt2.y - pt1.y);
    const scaleFt = this.currentScaleFtPerPt || 0.111111;
    const lengthLf = (distPt * scaleFt).toFixed(2);
    const activeTag = document.getElementById('active-partition-tag')?.value || '5E';

    // 1. Highlight Band
    const band = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    band.setAttribute('x1', pt1.pxX);
    band.setAttribute('y1', pt1.pxY);
    band.setAttribute('x2', pt2.pxX);
    band.setAttribute('y2', pt2.pxY);
    band.setAttribute('stroke-width', Math.max(16 * this.ptToPxRatio, 14));
    band.setAttribute('class', 'rubberband-band');

    // 2. Centerline Spine
    const spine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    spine.setAttribute('x1', pt1.pxX);
    spine.setAttribute('y1', pt1.pxY);
    spine.setAttribute('x2', pt2.pxX);
    spine.setAttribute('y2', pt2.pxY);
    spine.setAttribute('stroke-width', Math.max(2.5 * this.ptToPxRatio, 2));
    spine.setAttribute('class', 'rubberband-spine');

    // 3. Start & End points
    const p1 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    p1.setAttribute('cx', pt1.pxX);
    p1.setAttribute('cy', pt1.pxY);
    p1.setAttribute('r', '5');
    p1.setAttribute('fill', '#ffffff');
    p1.setAttribute('stroke', '#dc2626');
    p1.setAttribute('stroke-width', '2');

    const p2 = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    p2.setAttribute('cx', pt2.pxX);
    p2.setAttribute('cy', pt2.pxY);
    p2.setAttribute('r', '5');
    p2.setAttribute('fill', '#ffffff');
    p2.setAttribute('stroke', '#dc2626');
    p2.setAttribute('stroke-width', '2');

    // 4. Live length badge
    const midX = (pt1.pxX + pt2.pxX) / 2;
    const midY = (pt1.pxY + pt2.pxY) / 2;
    const label = `${activeTag} · ${lengthLf} LF`;

    const badgeWidth = label.length * 8 + 14;
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', midX - badgeWidth / 2);
    rect.setAttribute('y', midY - 22);
    rect.setAttribute('width', badgeWidth);
    rect.setAttribute('height', '18');
    rect.setAttribute('fill', '#070b13');
    rect.setAttribute('stroke', '#ef4444');
    rect.setAttribute('stroke-width', '1.5');

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', midX);
    text.setAttribute('y', midY - 10);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', '#ffffff');
    text.setAttribute('font-size', '10px');
    text.setAttribute('font-family', 'JetBrains Mono, monospace');
    text.setAttribute('font-weight', 'bold');
    text.textContent = label;

    group.appendChild(band);
    group.appendChild(spine);
    group.appendChild(p1);
    group.appendChild(p2);
    group.appendChild(rect);
    group.appendChild(text);
  }

  _showHoverHUD(wall, e) {
    const hud = document.getElementById('cad-hover-hud');
    if (!hud) return;
    const titleEl = document.getElementById('cad-hud-title');
    const badgeEl = document.getElementById('cad-hud-badge');
    const lfEl = document.getElementById('cad-hud-lf');
    const thickEl = document.getElementById('cad-hud-thick');
    const heightEl = document.getElementById('cad-hud-height');
    const calloutEl = document.getElementById('cad-hud-callout');

    const isVerified = !!wall.is_height_verified && wall.status !== 'REVIEW';
    if (titleEl) titleEl.innerHTML = `<span>TAG ${wall.tag || 'DRW'} [${wall.run_id}]</span>`;
    if (badgeEl) {
      badgeEl.textContent = isVerified ? 'VERIFIED' : 'REVIEW';
      badgeEl.className = isVerified
        ? 'px-1 py-0.2 text-[9px] bg-emerald-950/60 text-emerald-400 border border-emerald-500/30 font-bold'
        : 'px-1 py-0.2 text-[9px] bg-amber-950/60 text-amber-400 border border-amber-500/30 font-bold';
    }
    if (lfEl) lfEl.textContent = `${(wall.net_length_ft || 0).toFixed(2)}'`;
    if (thickEl) {
      const isM = !!wall.thickness_measured;
      thickEl.textContent = wall.thickness_in ? `${Number(wall.thickness_in).toFixed(2)}" (${isM ? 'M' : 'Nom'})` : '—';
      thickEl.className = isM ? 'text-emerald-400 font-bold' : 'text-white font-bold';
    }
    if (heightEl) heightEl.textContent = `${Number(wall.height_ft || 10).toFixed(1)}'`;
    if (calloutEl) {
      calloutEl.textContent = wall.section_callout_tag || 'None';
      calloutEl.className = wall.section_callout_tag ? 'text-primary font-bold' : 'text-[#64748b]';
    }

    this._moveHoverHUD(e);
    hud.classList.remove('hidden');
  }

  _moveHoverHUD(e) {
    const hud = document.getElementById('cad-hover-hud');
    if (!hud) return;
    const rect = this.container.getBoundingClientRect();
    const x = e.clientX - rect.left + 14;
    const y = e.clientY - rect.top + 14;
    hud.style.left = `${x}px`;
    hud.style.top = `${y}px`;
  }

  _hideHoverHUD() {
    const hud = document.getElementById('cad-hover-hud');
    if (hud) hud.classList.add('hidden');
  }
}

window.CADCanvasViewer = CADCanvasViewer;
