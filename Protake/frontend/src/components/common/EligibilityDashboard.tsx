/**
 * components/common/EligibilityDashboard.tsx
 *
 * Comprehensive eligibility dashboard showing production-grade sheet eligibility
 * analysis with detailed evidence, confidence scoring, and actionable recommendations.
 */

import { useMemo, useState } from "react";
import { 
  CheckCircle, 
  AlertTriangle, 
  XCircle, 
  Info, 
  Eye, 
  Filter,
  BarChart3,
  Target,
  FileText,
  Settings
} from "lucide-react";
import { useApp } from "@/state/AppContext";
import { useSheetContext } from "@/state/SheetContextProvider";
import { 
  assessMultipleSheets, 
  getEligibilityProjectSummary,
  type EligibilityLevel,
  type EligibilityAssessment 
} from "@/lib/sheetEligibilityEngine";

export default function EligibilityDashboard() {
  const { state } = useApp();
  const { allSheetContexts, activeSheetContext } = useSheetContext();
  
  const [selectedLevel, setSelectedLevel] = useState<EligibilityLevel | "all">("all");
  const [showDetails, setShowDetails] = useState(false);
  const [selectedAssessment, setSelectedAssessment] = useState<EligibilityAssessment | null>(null);
  const [selectedSheetId, setSelectedSheetId] = useState<string | null>(null);
  
  // Run comprehensive eligibility assessments
  const eligibilityAssessments = useMemo(() => {
    const contexts = Object.fromEntries(
      Object.entries(allSheetContexts).map(([id, context]) => [
        id, 
        {
          discipline: context.discipline,
          drawingType: context.drawingType,
          scale: context.scale
        }
      ])
    );
    
    return assessMultipleSheets(state.sheets, state.detections, contexts);
  }, [state.sheets, state.detections, allSheetContexts]);
  
  // Project summary
  const projectSummary = useMemo(() => {
    return getEligibilityProjectSummary(eligibilityAssessments);
  }, [eligibilityAssessments]);
  
  // Active sheet assessment
  const activeAssessment = activeSheetContext 
    ? eligibilityAssessments[activeSheetContext.sheetId] 
    : null;
  
  // Filtered assessments
  const filteredAssessments = Object.entries(eligibilityAssessments).filter(([_, assessment]) => {
    return selectedLevel === "all" || assessment.level === selectedLevel;
  });
  
  const getLevelIcon = (level: EligibilityLevel) => {
    switch (level) {
      case "fully_eligible": return <CheckCircle size={16} className="text-green-400" />;
      case "walls_only": return <CheckCircle size={16} className="text-yellow-400" />;
      case "ceiling_only": return <CheckCircle size={16} className="text-blue-400" />;
      case "reference_authority": return <Info size={16} className="text-cyan-400" />;
      case "dimensional_reference": return <Info size={16} className="text-purple-400" />;
      case "not_eligible": return <XCircle size={16} className="text-gray-500" />;
      case "needs_classification": return <AlertTriangle size={16} className="text-red-400" />;
      default: return <AlertTriangle size={16} className="text-gray-400" />;
    }
  };
  
  const getLevelColor = (level: EligibilityLevel): string => {
    switch (level) {
      case "fully_eligible": return "text-green-400";
      case "walls_only": return "text-yellow-400";
      case "ceiling_only": return "text-blue-400";
      case "reference_authority": return "text-cyan-400";
      case "dimensional_reference": return "text-purple-400";
      case "not_eligible": return "text-gray-500";
      case "needs_classification": return "text-red-400";
      default: return "text-gray-400";
    }
  };
  
  const formatLevel = (level: EligibilityLevel): string => {
    return level.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };
  
  return (
    <div className="bg-[#0B0E14] border-b border-white/10 p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Target className="text-blue-400" size={20} />
          <h2 className="text-lg font-bold text-white">Sheet Eligibility Analysis</h2>
          <div className="text-sm text-gray-400">
            {projectSummary.totalSheets} sheets • {projectSummary.fullyEligible} fully eligible
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className={`px-3 py-1 rounded text-xs transition-colors ${
              showDetails ? "bg-blue-600/20 text-blue-400" : "text-gray-400 hover:text-white"
            }`}
          >
            <Eye size={14} className="inline mr-1" />
            Details
          </button>
        </div>
      </div>
      
      {/* Project Summary Cards */}
      <div className="grid grid-cols-6 gap-3">
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">FULLY ELIGIBLE</div>
          <div className="text-lg font-bold text-green-400">
            {projectSummary.byLevel.fully_eligible || 0}
          </div>
          <div className="text-xs text-gray-500">
            Complete takeoff capability
          </div>
        </div>
        
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">PARTIAL ELIGIBLE</div>
          <div className="text-lg font-bold text-yellow-400">
            {(projectSummary.byLevel.walls_only || 0) + (projectSummary.byLevel.ceiling_only || 0)}
          </div>
          <div className="text-xs text-gray-500">
            Limited takeoff capability
          </div>
        </div>
        
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">REFERENCE ONLY</div>
          <div className="text-lg font-bold text-cyan-400">
            {(projectSummary.byLevel.reference_authority || 0) + (projectSummary.byLevel.dimensional_reference || 0)}
          </div>
          <div className="text-xs text-gray-500">
            Schedule/spec authority
          </div>
        </div>
        
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">NOT ELIGIBLE</div>
          <div className="text-lg font-bold text-gray-500">
            {projectSummary.byLevel.not_eligible || 0}
          </div>
          <div className="text-xs text-gray-500">
            No takeoff capability
          </div>
        </div>
        
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">NEEDS REVIEW</div>
          <div className="text-lg font-bold text-red-400">
            {projectSummary.needsReview}
          </div>
          <div className="text-xs text-gray-500">
            Manual classification
          </div>
        </div>
        
        <div className="bg-[#111622] border border-white/10 rounded-lg p-3">
          <div className="text-xs text-gray-400 mb-1">AVG CONFIDENCE</div>
          <div className="text-lg font-bold text-white">
            {(projectSummary.averageConfidence * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-gray-500">
            Assessment confidence
          </div>
        </div>
      </div>
      
      {/* Active Sheet Assessment */}
      {activeAssessment && (
        <div className="bg-[#111622] border border-white/10 rounded-lg p-4">
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                {getLevelIcon(activeAssessment.level)}
                <span className="font-bold text-white">
                  {activeSheetContext?.sheetCode} - {formatLevel(activeAssessment.level)}
                </span>
                <div className="px-2 py-0.5 rounded text-xs bg-white/10 text-gray-300">
                  {(activeAssessment.confidence * 100).toFixed(0)}% confidence
                </div>
              </div>
              <div className="text-sm text-gray-400">
                {activeAssessment.reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
              </div>
            </div>
            
            <button
              onClick={() => setSelectedAssessment(activeAssessment)}
              className="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded hover:bg-blue-600/10"
            >
              View Details
            </button>
          </div>
          
          {/* Trade Capabilities */}
          <div className="grid grid-cols-6 gap-2 mb-3">
            {Object.entries(activeAssessment.tradeCapabilities).map(([trade, capable]) => (
              <div 
                key={trade}
                className={`px-2 py-1 rounded text-xs text-center ${
                  capable ? "bg-green-600/20 text-green-400" : "bg-gray-600/20 text-gray-500"
                }`}
              >
                {trade.charAt(0).toUpperCase() + trade.slice(1)}
              </div>
            ))}
          </div>
          
          {/* Evidence Summary */}
          <div className="grid grid-cols-4 gap-3 text-xs">
            <div>
              <div className="text-gray-500">Walls</div>
              <div className="text-white">
                {activeAssessment.evidence.wallCount} 
                <span className="text-gray-400 ml-1">
                  ({(activeAssessment.evidence.wallQuality * 100).toFixed(0)}%)
                </span>
              </div>
            </div>
            
            <div>
              <div className="text-gray-500">Rooms</div>
              <div className="text-white">
                {activeAssessment.evidence.roomCount}
                <span className="text-gray-400 ml-1">
                  ({(activeAssessment.evidence.roomQuality * 100).toFixed(0)}%)
                </span>
              </div>
            </div>
            
            <div>
              <div className="text-gray-500">Openings</div>
              <div className="text-white">
                {activeAssessment.evidence.openingCount}
                <span className="text-gray-400 ml-1">
                  ({(activeAssessment.evidence.openingQuality * 100).toFixed(0)}%)
                </span>
              </div>
            </div>
            
            <div>
              <div className="text-gray-500">Overall Quality</div>
              <div className="text-white">
                {(activeAssessment.evidence.overallDetectionQuality * 100).toFixed(0)}%
              </div>
            </div>
          </div>
          
          {/* Primary Factors */}
          {activeAssessment.primaryFactors.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/5">
              <div className="text-xs text-gray-500 mb-1">Primary Factors:</div>
              <div className="text-xs text-gray-300">
                {activeAssessment.primaryFactors.join(" • ")}
              </div>
            </div>
          )}
          
          {/* Limiting Factors */}
          {activeAssessment.limitingFactors.length > 0 && (
            <div className="mt-2">
              <div className="text-xs text-gray-500 mb-1">Limiting Factors:</div>
              <div className="text-xs text-yellow-400">
                {activeAssessment.limitingFactors.join(" • ")}
              </div>
            </div>
          )}
          
          {/* Recommendations */}
          {activeAssessment.recommendations.length > 0 && (
            <div className="mt-2">
              <div className="text-xs text-gray-500 mb-1">Recommendations:</div>
              <div className="text-xs text-blue-400">
                {activeAssessment.recommendations.join(" • ")}
              </div>
            </div>
          )}
        </div>
      )}
      
      {/* Filter Bar */}
      <div className="flex items-center gap-3">
        <Filter size={16} className="text-gray-400" />
        <select
          value={selectedLevel}
          onChange={(e) => setSelectedLevel(e.target.value as EligibilityLevel | "all")}
          className="bg-[#1A1F2E] border border-white/10 rounded px-3 py-1 text-sm text-gray-300"
        >
          <option value="all">All Levels ({projectSummary.totalSheets})</option>
          <option value="fully_eligible">Fully Eligible ({projectSummary.byLevel.fully_eligible || 0})</option>
          <option value="walls_only">Walls Only ({projectSummary.byLevel.walls_only || 0})</option>
          <option value="ceiling_only">Ceiling Only ({projectSummary.byLevel.ceiling_only || 0})</option>
          <option value="reference_authority">Reference Authority ({projectSummary.byLevel.reference_authority || 0})</option>
          <option value="not_eligible">Not Eligible ({projectSummary.byLevel.not_eligible || 0})</option>
          <option value="needs_classification">Needs Review ({projectSummary.byLevel.needs_classification || 0})</option>
        </select>
        
        <div className="text-sm text-gray-400">
          Showing {filteredAssessments.length} of {projectSummary.totalSheets} sheets
        </div>
      </div>
      
      {/* Sheet List */}
      {showDetails && (
        <div className="bg-[#111622] border border-white/10 rounded-lg overflow-hidden">
          <div className="p-3 border-b border-white/5">
            <h3 className="font-bold text-white text-sm">Sheet Assessment Details</h3>
          </div>
          
          <div className="max-h-60 overflow-y-auto">
            {filteredAssessments.map(([sheetId, assessment]) => {
              const sheetContext = allSheetContexts[sheetId];
              
              return (
                <div
                  key={sheetId}
                  className="p-3 border-b border-white/5 hover:bg-white/5 cursor-pointer"
                  onClick={() => {
                    setSelectedAssessment(assessment);
                    setSelectedSheetId(sheetId);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {getLevelIcon(assessment.level)}
                      <div>
                        <div className="font-medium text-white text-sm">
                          {sheetContext?.sheetCode} - {sheetContext?.sheetTitle}
                        </div>
                        <div className="text-xs text-gray-400">
                          {formatLevel(assessment.level)} • {(assessment.confidence * 100).toFixed(0)}% confidence
                        </div>
                      </div>
                    </div>
                    
                    <div className="text-xs text-gray-500">
                      {assessment.evidence.wallCount}w {assessment.evidence.roomCount}r {assessment.evidence.openingCount}o
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      
      {/* Detail Modal — real formatted breakdown, not a raw JSON dump, so a
          reviewer can actually read why the assessment landed where it did. */}
      {selectedAssessment && (() => {
        const sheetContext = selectedSheetId ? allSheetContexts[selectedSheetId] : null;
        const a = selectedAssessment;
        const tradeLabels: Record<keyof typeof a.tradeCapabilities, string> = {
          drywall: "Drywall", painting: "Painting", flooring: "Flooring",
          ceiling: "Ceiling", roofing: "Roofing", openings: "Openings",
        };
        return (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
            onClick={() => { setSelectedAssessment(null); setSelectedSheetId(null); }}
          >
            <div
              className="bg-[#0B0E14] border border-white/20 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-bold text-white">
                    {sheetContext ? `${sheetContext.sheetCode} — ${sheetContext.sheetTitle}` : "Assessment Details"}
                  </h3>
                  <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2">
                    {getLevelIcon(a.level)}
                    <span className={getLevelColor(a.level)}>{formatLevel(a.level)}</span>
                    <span>•</span>
                    <span>{(a.confidence * 100).toFixed(0)}% confidence</span>
                  </div>
                </div>
                <button
                  onClick={() => { setSelectedAssessment(null); setSelectedSheetId(null); }}
                  className="text-gray-400 hover:text-white"
                >
                  ×
                </button>
              </div>

              <div className="space-y-4 text-sm">
                {/* Trade capabilities */}
                <div>
                  <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Trade Capabilities</div>
                  <div className="flex flex-wrap gap-1.5">
                    {(Object.keys(a.tradeCapabilities) as (keyof typeof a.tradeCapabilities)[]).map((trade) => (
                      <span
                        key={trade}
                        className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
                          a.tradeCapabilities[trade]
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : "bg-gray-500/10 text-gray-500 border-gray-500/20"
                        }`}
                      >
                        {tradeLabels[trade]}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Detection evidence */}
                <div>
                  <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Detection Evidence</div>
                  <div className="grid grid-cols-3 gap-2 text-xs text-gray-300">
                    <div>{a.evidence.wallCount} walls ({(a.evidence.wallQuality * 100).toFixed(0)}% avg conf.)</div>
                    <div>{a.evidence.roomCount} rooms ({(a.evidence.roomQuality * 100).toFixed(0)}% avg conf.)</div>
                    <div>{a.evidence.openingCount} openings ({(a.evidence.openingQuality * 100).toFixed(0)}% avg conf.)</div>
                    <div>{a.evidence.architecturalWalls} architectural</div>
                    <div>{a.evidence.structuralWalls} structural</div>
                    <div>{a.evidence.unclassifiedWalls} needs review</div>
                  </div>
                </div>

                {/* Primary / limiting factors */}
                {a.primaryFactors.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Supporting Factors</div>
                    <ul className="list-disc list-inside text-xs text-gray-300 space-y-0.5">
                      {a.primaryFactors.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
                {a.limitingFactors.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-yellow-500/80 uppercase tracking-wider mb-1.5">Limiting Factors</div>
                    <ul className="list-disc list-inside text-xs text-yellow-200/80 space-y-0.5">
                      {a.limitingFactors.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
                {a.recommendations.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-blue-400/80 uppercase tracking-wider mb-1.5">Recommendations</div>
                    <ul className="list-disc list-inside text-xs text-blue-200/80 space-y-0.5">
                      {a.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}

                <div className="pt-2 border-t border-white/5 text-[10px] text-gray-500">
                  Assessment v{a.assessmentVersion} • {new Date(a.assessmentTimestamp).toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}