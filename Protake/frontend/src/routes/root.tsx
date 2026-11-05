import { Outlet, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import MenuBar from "@/components/common/MenuBar";
import CommandPalette from "@/components/common/CommandPalette";
import ReportModal from "@/components/reports/ReportModal";
import SettingsModal from "@/components/common/SettingsModal";
import EligibilityDashboardModal from "@/components/common/EligibilityDashboardModal";
import GlobalShortcuts from "@/components/common/GlobalShortcuts";

export default function Root() {
  const location = useLocation();
  const isUploadPage = location.pathname === "/upload" || location.pathname === "/";

  return (
    <div className="h-screen w-screen bg-[var(--color-bg)] text-[var(--color-text-primary)] antialiased flex flex-col overflow-hidden">
      {isUploadPage && <MenuBar />}
      <div className={`flex-1 min-h-0 relative ${isUploadPage ? "overflow-y-auto" : ""}`}>
        <Outlet />
      </div>
      <CommandPalette />
      <ReportModal />
      <SettingsModal />
      <EligibilityDashboardModal />
      <GlobalShortcuts />
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#15171C",
            border: "1px solid #1E293B",
            color: "#F8FAFC",
          },
        }}
      />
    </div>
  );
}

export function ErrorBoundary() {
  return (
    <div className="h-screen w-screen bg-[#0E1116] text-[#F8FAFC] flex flex-col items-center justify-center p-6 text-center">
      <div className="max-w-md p-6 rounded-xl border border-rose-500/30 bg-rose-950/20 shadow-2xl space-y-4">
        <h2 className="text-lg font-bold text-rose-400">Application Error Encountered</h2>
        <p className="text-xs text-gray-300">
          An unexpected rendering state occurred. Click below to refresh the workspace.
        </p>
        <button
          onClick={() => (window.location.href = "/workspace")}
          className="px-4 py-2 rounded-lg bg-cyan-500 text-black font-semibold text-xs hover:bg-cyan-400 transition-colors cursor-pointer"
        >
          Reload Workspace
        </button>
      </div>
    </div>
  );
}
