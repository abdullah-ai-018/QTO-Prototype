/**
 * components/common/ScopeAwareComponent.tsx
 *
 * Example component demonstrating proper data scope consumption.
 * Every component should declare which scope it operates on and validate its data source.
 */

import { useProjectScope, useSheetScope, useWallScope } from "@/state/DataScopeContext";

// Example 1: PROJECT SCOPE component
export function ProjectSummaryCard() {
  const projectScope = useProjectScope();
  
  return (
    <div className="p-4 bg-gray-800 rounded-lg">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
        PROJECT TOTALS
      </h3>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span>Total Sheets:</span>
          <span className="font-mono">{projectScope.totalSheets}</span>
        </div>
        <div className="flex justify-between">
          <span>Total Walls:</span>
          <span className="font-mono">{projectScope.totalWalls}</span>
        </div>
        <div className="flex justify-between">
          <span>Direct Cost:</span>
          <span className="font-mono">${(projectScope.liveQtoTotals?.directCost ?? 0).toLocaleString()}</span>
        </div>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        Calculated: {projectScope.lastCalculated}
      </div>
    </div>
  );
}

// Example 2: SHEET SCOPE component
export function CurrentSheetCard() {
  const sheetScope = useSheetScope();
  
  if (!sheetScope) {
    return (
      <div className="p-4 bg-gray-800 rounded-lg">
        <div className="text-gray-500">No sheet selected</div>
      </div>
    );
  }
  
  return (
    <div className="p-4 bg-gray-800 rounded-lg">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
        CURRENT SHEET: {sheetScope.sheetCode}
      </h3>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span>Eligible:</span>
          <span className={`font-mono ${sheetScope.takeoffEligible ? 'text-green-400' : 'text-amber-400'}`}>
            {sheetScope.takeoffEligible ? 'Yes' : 'No'}
          </span>
        </div>
        {!sheetScope.takeoffEligible && (
          <div className="text-xs text-gray-500">
            Reason: {sheetScope.eligibilityReason}
          </div>
        )}
        <div className="flex justify-between">
          <span>Walls:</span>
          <span className="font-mono">{sheetScope.wallCount}</span>
        </div>
        <div className="flex justify-between">
          <span>Rooms:</span>
          <span className="font-mono">{sheetScope.roomCount}</span>
        </div>
        <div className="flex justify-between">
          <span>Direct Cost:</span>
          <span className="font-mono">${sheetScope.takeoffResult.directCost.toLocaleString()}</span>
        </div>
      </div>
      <div className="mt-2 text-xs text-gray-500">
        Scale: {sheetScope.scaleSource} ({sheetScope.scale.toFixed(2)} px/ft)
      </div>
    </div>
  );
}

// Example 3: WALL SCOPE component
export function SelectedWallCard() {
  const wallScope = useWallScope();
  
  if (!wallScope) {
    return (
      <div className="p-4 bg-gray-800 rounded-lg">
        <div className="text-gray-500">No wall selected</div>
      </div>
    );
  }
  
  return (
    <div className="p-4 bg-gray-800 rounded-lg">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
        SELECTED WALL: {wallScope.wallId.slice(-8)}
      </h3>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span>Category:</span>
          <span className="font-mono text-blue-400">{wallScope.category}</span>
        </div>
        <div className="flex justify-between">
          <span>Length:</span>
          <span className="font-mono">{wallScope.lengthFt.toFixed(1)} ft</span>
        </div>
        <div className="flex justify-between">
          <span>Height:</span>
          <span className="font-mono">{wallScope.heightFt.toFixed(1)} ft ({wallScope.heightSource})</span>
        </div>
        <div className="flex justify-between">
          <span>Thickness:</span>
          <span className="font-mono">{(wallScope.thicknessFt * 12).toFixed(1)}" ({wallScope.thicknessSource})</span>
        </div>
        <div className="flex justify-between">
          <span>Net Area:</span>
          <span className="font-mono">{wallScope.netHangAreaSqFt.toFixed(1)} SF</span>
        </div>
        <div className="flex justify-between">
          <span>Openings:</span>
          <span className="font-mono">{wallScope.openings.length}</span>
        </div>
        <div className="flex justify-between">
          <span>QTO Eligible:</span>
          <span className={`font-mono ${wallScope.qtoEligible ? 'text-green-400' : 'text-red-400'}`}>
            {wallScope.qtoEligible ? 'Yes' : 'No'}
          </span>
        </div>
        {!wallScope.qtoEligible && wallScope.qtoBlockReason && (
          <div className="text-xs text-red-400">
            Block Reason: {wallScope.qtoBlockReason}
          </div>
        )}
      </div>
      <div className="mt-2 text-xs text-gray-500">
        Status: {wallScope.status} | Confidence: {(wallScope.confidence * 100).toFixed(1)}%
      </div>
    </div>
  );
}

// Example 4: Multi-scope comparison component
export function ScopeComparisonCard() {
  const projectScope = useProjectScope();
  const sheetScope = useSheetScope();
  
  return (
    <div className="p-4 bg-gray-800 rounded-lg">
      <h3 className="text-sm font-bold text-gray-400 uppercase tracking-wider mb-2">
        SCOPE COMPARISON
      </h3>
      <div className="space-y-2">
        <div>
          <div className="text-xs text-gray-500 mb-1">PROJECT vs CURRENT SHEET</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="text-gray-400">Metric</div>
            <div className="text-blue-400">Project</div>
            <div className="text-green-400">Sheet</div>
            
            <div>Walls</div>
            <div className="font-mono">{projectScope.totalWalls}</div>
            <div className="font-mono">{sheetScope?.wallCount || 0}</div>
            
            <div>Cost</div>
            <div className="font-mono">${(projectScope.liveQtoTotals?.directCost ?? 0).toLocaleString()}</div>
            <div className="font-mono">${sheetScope?.takeoffResult.directCost.toLocaleString() || '0'}</div>
          </div>
        </div>
      </div>
      <div className="mt-2 text-xs text-amber-400">
        ⚠ Never mix these scopes in calculations
      </div>
    </div>
  );
}