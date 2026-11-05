import type { AppState } from "@/state/appState";
import { toast } from "sonner";

export function saveProject(state: AppState) {
  const data = {
    version: "protake-v1",
    timestamp: Date.now(),
    revision: state.revision,
    file: state.file,
    sheets: state.sheets,
    activeSheetId: state.activeSheetId,
    detections: state.detections,
    measurements: state.measurements,
    callouts: state.callouts,
    stickyNotes: state.stickyNotes,
    calibration: state.calibration,
  };

  try {
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeName = (state.file?.name || "project").replace(/\.[^/.]+$/, "");
    a.href = url;
    a.download = `protake-takeoff-${safeName}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Project saved", { description: `Revision ${state.revision} saved to protake-takeoff-${safeName}.json` });
  } catch (err) {
    console.error("Failed to save project:", err);
    toast.error("Failed to save project");
  }
}
