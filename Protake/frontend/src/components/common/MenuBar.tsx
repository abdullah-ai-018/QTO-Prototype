import { useRef, useState } from "react";
import { useApp } from "@/state/AppContext";
import { useNavigate } from "react-router-dom";
import { Settings, Layers, FolderOpen, Zap } from "lucide-react";
import { toast } from "sonner";
import Logo from "@/components/common/Logo";
import TradeSelectModal from "@/components/common/TradeSelectModal";
import type { TradeId } from "@/types";
import { SAMPLE_SHEETS, generateSampleDetections, seedHistory } from "@/lib/sampleData";

function sleep(ms: number) {
  return new Promise((res) => setTimeout(res, ms));
}

export default function MenuBar() {
  const { state, dispatch } = useApp();
  const navigate = useNavigate();
  const restoreRef = useRef<HTMLInputElement>(null);
  const [showTradeSelectModal, setShowTradeSelectModal] = useState(false);

  const handleSettingsClick = () => {
    dispatch({ type: "OPEN_SETTINGS" });
  };

  const handleAvatarClick = () => {
    toast.info("Guest Estimator Mode", {
      description: "Logged in as guest@protake.app. Local session changes are preserved.",
    });
  };

  const handleNewTakeoff = () => {
    dispatch({ type: "RESET_PROJECT" });
    navigate("/");
    toast.success("Blueprint Intake Reset", {
      description: "Ready to upload a new drawing set.",
    });
  };

  async function handleRestoreFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      if (data.version !== "protake-v1") {
        throw new Error("Invalid file format. This is not a Protake project save file.");
      }

      let objectUrl = data.file?.objectUrl;
      if (data.file?.base64) {
        toast.info("Reconstructing blueprint from project file...");
        const res = await fetch(data.file.base64);
        const blob = await res.blob();
        objectUrl = URL.createObjectURL(blob);
      }

      const restoredState = {
        revision: data.revision,
        file: data.file ? { ...data.file, objectUrl } : null,
        sheets: data.sheets,
        activeSheetId: data.activeSheetId,
        detections: data.detections,
        measurements: data.measurements,
        callouts: data.callouts || [],
        stickyNotes: data.stickyNotes || [],
        calibration: data.calibration || {},
        uploadStage: "complete" as const,
      };

      dispatch({ type: "RESTORE_PROJECT", projectState: restoredState });
      toast.success("Project restored successfully", { description: data.file?.name });
      navigate("/workspace");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse file";
      toast.error("Restore failed", { description: msg });
    }
  }

  async function handleSelectTrade(trade: TradeId | "all") {
    setShowTradeSelectModal(false);

    if (trade === "all") {
      dispatch({ type: "RESET_VISIBILITY" });
    } else {
      dispatch({ type: "SET_SINGLE_ACTIVE_TRADE", trade });
    }

    // Ingest sample project
    dispatch({
      type: "SET_FILE",
      file: { name: "Commercial_Office_Tower_Set.pdf", sizeBytes: 4_213_880, numPages: 3, isSample: true },
    });
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "uploading" });
    dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 30 });
    await sleep(120);
    dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 65 });
    await sleep(120);
    dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 100 });
    
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "processing" });
    dispatch({ type: "SET_SCAN_PROGRESS", progress: 35 });
    await sleep(170);
    dispatch({ type: "SET_SCAN_PROGRESS", progress: 70 });
    await sleep(170);
    dispatch({ type: "SET_SCAN_PROGRESS", progress: 100 });

    dispatch({ type: "SET_SHEETS", sheets: SAMPLE_SHEETS });
    dispatch({ type: "SET_NUM_PAGES", numPages: SAMPLE_SHEETS.length });

    const sampleDetections = SAMPLE_SHEETS.flatMap((s) => generateSampleDetections(s.id));
    
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "detecting" });
    dispatch({ type: "START_SCAN" });
    
    for (const p of [15, 35, 58, 76, 94, 100]) {
      await sleep(150);
      dispatch({ type: "SET_SCAN_PROGRESS", progress: p });
    }

    const landingSheet = SAMPLE_SHEETS.find((s) => s.isTakeoffEligible !== false) ?? SAMPLE_SHEETS[0];

    let filteredDetections = sampleDetections;
    if (trade !== "all") {
      const fetchRooms = ["painting", "flooring", "roofing", "drywall"].includes(trade);
      const fetchWalls = ["drywall"].includes(trade);
      const fetchDetections = ["painting", "furniture", "openings"].includes(trade);

      filteredDetections = sampleDetections.filter((d) => {
        if (d.kind === "room") return fetchRooms;
        if (d.kind === "wall") return fetchWalls;
        if (["door", "window"].includes(d.kind)) return trade === "openings" || trade === "painting";
        return fetchDetections;
      });
    }

    dispatch({ type: "FINISH_SCAN", detections: filteredDetections });
    seedHistory().forEach((h) => dispatch({ type: "ADD_HISTORY", entry: h }));
    dispatch({ type: "SET_ACTIVE_SHEET", sheetId: landingSheet.id });
    await sleep(200);
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });

    const roomCount = filteredDetections.filter((d) => d.kind === "room").length;
    const wallCount = filteredDetections.filter((d) => d.kind === "wall").length;
    const symbolCount = filteredDetections.filter((d) => d.kind === "door" || d.kind === "window").length;

    toast.success(
      `${roomCount} rooms, ${wallCount} walls${symbolCount > 0 ? `, ${symbolCount} doors/windows` : ""} loaded`,
      { description: `AI geometry engine initialized for ${trade === "all" ? "all trades" : trade}.` }
    );
    navigate(`/workspace?blueprint_id=sample`);
  }

  return (
    <>
      <header className="fixed top-0 left-0 w-full z-50 border-b border-white/10 bg-[#0f0f0f]/80 backdrop-blur-md shadow-sm select-none h-14">
        <div className="max-w-6xl mx-auto px-6 h-full w-full flex justify-between items-center">
          <div className="flex items-center gap-10">
            <div 
              onClick={() => navigate("/")}
              className="flex items-center gap-3 cursor-pointer"
            >
              <div className="w-7 h-7 relative">
                <Logo />
              </div>
              <span className="font-semibold tracking-tight text-sm text-white">Protake</span>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <button 
              onClick={() => restoreRef.current?.click()}
              title="Open Project"
              className="border border-white/10 hover:bg-white/5 text-white p-2 rounded-lg transition-all cursor-pointer flex items-center justify-center"
            >
              <FolderOpen size={16} className="text-[#94a3b8]" />
            </button>
            <input
              ref={restoreRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleRestoreFile}
            />

            <button 
              onClick={() => setShowTradeSelectModal(true)}
              title="Load Sample Project"
              className="border border-white/10 hover:bg-white/5 text-white p-2 rounded-lg transition-all cursor-pointer flex items-center justify-center"
            >
              <Zap size={16} className="text-amber-400" />
            </button>

            <button
              onClick={handleSettingsClick}
              title="Takeoff settings"
              className="text-[#94a3b8] hover:text-white transition-colors duration-200 cursor-pointer ml-1"
            >
              <Settings size={16} />
            </button>
            <div
              onClick={handleAvatarClick}
              className="h-8 w-8 rounded-full overflow-hidden border border-white/10 cursor-pointer"
            >
              <img 
                className="w-full h-full object-cover" 
                alt="User avatar" 
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuAKlL9avvUizgGiarzQLJ-WYpsgnQuhvSZAPfHaQwe1ianIYUURs_e_fyD9Ezw7ZIJc9r1-blMNCqyY7A5NePcMP3zb7EH9Xo6NcYpvXa2I2X2XK0tEfnZ4TN7cnLNxxXFoaQs659j2YWdW7PIIqreAwzBATdFD6ac6gTqcO1FL0IJIhJzO3QxrT3aDZdGo8wKND241tf5XhzFIHtY4Z4quCJY9hZ6sZmoTO_Ovefu3d78rX0p81fw"
              />
            </div>
            <button 
              onClick={handleNewTakeoff}
              className="bg-white text-black px-4 py-2 rounded-lg text-xs font-semibold hover:opacity-90 active:scale-95 transition-all cursor-pointer"
            >
              New Takeoff
            </button>
          </div>
        </div>
      </header>
      <TradeSelectModal
        open={showTradeSelectModal}
        onClose={() => setShowTradeSelectModal(false)}
        onSelect={handleSelectTrade}
      />
    </>
  );
}
