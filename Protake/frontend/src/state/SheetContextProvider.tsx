/**
 * state/SheetContextProvider.tsx
 *
 * React provider for engineering-grade sheet context system.
 * Provides comprehensive sheet metadata and engineering context.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useApp } from "./AppContext";
import type { EngineeringSheetContext } from "@/lib/sheetContext";
import { 
  buildAllSheetContexts, 
  getSheetContextSummary,
  type DrawingDiscipline,
  type DrawingType,
  type TakeoffEligibilityLevel
} from "@/lib/sheetContext";
import {
  assessMultipleSheets,
  getEligibilityProjectSummary,
  type EligibilityAssessment
} from "@/lib/sheetEligibilityEngine";

interface SheetContextValue {
  // All sheet contexts
  allSheetContexts: Record<string, EngineeringSheetContext>;
  
  // Active sheet context
  activeSheetContext: EngineeringSheetContext | null;
  
  // Project summary
  projectSummary: {
    totalSheets: number;
    byDiscipline: Record<DrawingDiscipline, number>;
    byType: Record<DrawingType, number>;
    byEligibility: Record<TakeoffEligibilityLevel, number>;
    needsReview: number;
    fullyCalibrated: number;
  };
  
  // Filtered contexts
  getSheetsByDiscipline: (discipline: DrawingDiscipline) => EngineeringSheetContext[];
  getSheetsByType: (type: DrawingType) => EngineeringSheetContext[];
  getSheetsByEligibility: (eligibility: TakeoffEligibilityLevel) => EngineeringSheetContext[];
  getTakeoffEligibleSheets: () => EngineeringSheetContext[];
  getSheetsNeedingReview: () => EngineeringSheetContext[];
  
  // Sheet navigation helpers
  getNextEligibleSheet: (currentSheetId: string) => EngineeringSheetContext | null;
  getPreviousEligibleSheet: (currentSheetId: string) => EngineeringSheetContext | null;
  getFirstEligibleSheet: () => EngineeringSheetContext | null;
}

const SheetContextContext = createContext<SheetContextValue | null>(null);

export function SheetContextProvider({ children }: { children: ReactNode }) {
  const { state } = useApp();
  
  // Build all sheet contexts
  const allSheetContexts = useMemo(() => {
    return buildAllSheetContexts(state.sheets, state.detections, state.calibration, state.file?.name);
  }, [state.sheets, state.detections, state.calibration, state.file?.name]);
  
  // Active sheet context
  const activeSheetContext = useMemo(() => {
    return state.activeSheetId ? allSheetContexts[state.activeSheetId] || null : null;
  }, [allSheetContexts, state.activeSheetId]);
  
  // Project summary
  const projectSummary = useMemo(() => {
    return getSheetContextSummary(allSheetContexts);
  }, [allSheetContexts]);
  
  // Filter functions
  const getSheetsByDiscipline = (discipline: DrawingDiscipline): EngineeringSheetContext[] => {
    return Object.values(allSheetContexts).filter(context => context.discipline === discipline);
  };
  
  const getSheetsByType = (type: DrawingType): EngineeringSheetContext[] => {
    return Object.values(allSheetContexts).filter(context => context.drawingType === type);
  };
  
  const getSheetsByEligibility = (eligibility: TakeoffEligibilityLevel): EngineeringSheetContext[] => {
    return Object.values(allSheetContexts).filter(context => context.eligibilityLevel === eligibility);
  };
  
  const getTakeoffEligibleSheets = (): EngineeringSheetContext[] => {
    return Object.values(allSheetContexts).filter(
      context => context.eligibilityLevel === "fully_eligible" || context.eligibilityLevel === "partial_eligible"
    );
  };
  
  const getSheetsNeedingReview = (): EngineeringSheetContext[] => {
    return Object.values(allSheetContexts).filter(context => context.engineeringStatus === "needs_review");
  };
  
  // Navigation helpers
  const getNextEligibleSheet = (currentSheetId: string): EngineeringSheetContext | null => {
    const eligibleSheets = getTakeoffEligibleSheets().sort((a, b) => a.sheetNumber - b.sheetNumber);
    const currentIndex = eligibleSheets.findIndex(sheet => sheet.sheetId === currentSheetId);
    
    if (currentIndex === -1 || currentIndex === eligibleSheets.length - 1) {
      return null;
    }
    
    return eligibleSheets[currentIndex + 1];
  };
  
  const getPreviousEligibleSheet = (currentSheetId: string): EngineeringSheetContext | null => {
    const eligibleSheets = getTakeoffEligibleSheets().sort((a, b) => a.sheetNumber - b.sheetNumber);
    const currentIndex = eligibleSheets.findIndex(sheet => sheet.sheetId === currentSheetId);
    
    if (currentIndex <= 0) {
      return null;
    }
    
    return eligibleSheets[currentIndex - 1];
  };
  
  const getFirstEligibleSheet = (): EngineeringSheetContext | null => {
    const eligibleSheets = getTakeoffEligibleSheets().sort((a, b) => a.sheetNumber - b.sheetNumber);
    return eligibleSheets[0] || null;
  };
  
  const value = useMemo(() => ({
    allSheetContexts,
    activeSheetContext,
    projectSummary,
    getSheetsByDiscipline,
    getSheetsByType,
    getSheetsByEligibility,
    getTakeoffEligibleSheets,
    getSheetsNeedingReview,
    getNextEligibleSheet,
    getPreviousEligibleSheet,
    getFirstEligibleSheet,
  }), [
    allSheetContexts,
    activeSheetContext,
    projectSummary,
    getSheetsByDiscipline,
    getSheetsByType,
    getSheetsByEligibility,
    getTakeoffEligibleSheets,
    getSheetsNeedingReview,
    getNextEligibleSheet,
    getPreviousEligibleSheet,
    getFirstEligibleSheet,
  ]);
  
  return (
    <SheetContextContext.Provider value={value}>
      {children}
    </SheetContextContext.Provider>
  );
}

export function useSheetContext() {
  const context = useContext(SheetContextContext);
  if (!context) {
    throw new Error("useSheetContext must be used within SheetContextProvider");
  }
  return context;
}

// Convenience hooks for specific use cases
export function useActiveSheetContext() {
  const { activeSheetContext } = useSheetContext();
  return activeSheetContext;
}

export function useProjectSheetSummary() {
  const { projectSummary } = useSheetContext();
  return projectSummary;
}

export function useTakeoffEligibleSheets() {
  const { getTakeoffEligibleSheets } = useSheetContext();
  return getTakeoffEligibleSheets();
}

export function useSheetNavigation() {
  const { getNextEligibleSheet, getPreviousEligibleSheet, getFirstEligibleSheet } = useSheetContext();
  return { getNextEligibleSheet, getPreviousEligibleSheet, getFirstEligibleSheet };
}