import { AnimatePresence, motion } from "framer-motion";
import { X, FileText, ExternalLink } from "lucide-react";

interface DocumentModalProps {
  open: boolean;
  fileName: string;
  fileUrl?: string;
  onClose: () => void;
}

export default function DocumentModal({ open, fileName, fileUrl, onClose }: DocumentModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-5xl h-[85vh] flex flex-col rounded-xl glass-panel glow-primary overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)]/95">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary)]">
                  <FileText size={16} />
                </div>
                <div>
                  <div className="text-sm font-semibold">{fileName}</div>
                  <div className="text-[10px] text-[var(--color-text-secondary)]">Original Document Viewer</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {fileUrl && (
                  <button
                    onClick={() => window.open(fileUrl, "_blank")}
                    title="Open in new tab"
                    className="w-8 h-8 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                  >
                    <ExternalLink size={15} />
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="w-8 h-8 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Document Content */}
            <div className="flex-1 bg-[#0b0d10] relative">
              {fileUrl ? (
                <iframe
                  src={fileUrl}
                  title={fileName}
                  className="w-full h-full border-none bg-white"
                />
              ) : (
                <div className="absolute inset-0 flex flex-col items-center justify-center text-[var(--color-text-secondary)] gap-2">
                  <FileText size={48} className="opacity-20" />
                  <span className="text-sm">Document not loaded or unavailable</span>
                </div>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
