import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_PREFIX = "qto:panel:";

interface UseResizablePanelOptions {
  min: number;
  max: number;
  defaultSize: number;
  /** "horizontal" drags left/right and resizes width; "vertical" drags up/down and resizes height. */
  axis: "horizontal" | "vertical";
  /** For a panel whose handle is on its LEFT/TOP edge, dragging right/down should shrink it, not grow it. */
  invert?: boolean;
}

interface UseResizablePanelResult {
  size: number;
  isDragging: boolean;
  handleProps: {
    onPointerDown: (e: React.PointerEvent) => void;
  };
}

function readStoredSize(key: string, min: number, max: number, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + key);
    if (raw == null) return fallback;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.min(max, Math.max(min, parsed));
  } catch {
    return fallback;
  }
}

/**
 * Local, persisted (localStorage) drag-to-resize for a single chrome panel
 * (sidebar width, inspector width, bottom panel height). Not part of
 * AppState: panel chrome size is a per-viewer UI preference, not takeoff
 * data, so it doesn't belong in the undo/redo-tracked reducer.
 */
export function useResizablePanel(key: string, options: UseResizablePanelOptions): UseResizablePanelResult {
  const { min, max, defaultSize, axis, invert = false } = options;
  const [size, setSize] = useState<number>(() => readStoredSize(key, min, max, defaultSize));
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<{ pointer: number; size: number } | null>(null);

  useEffect(() => {
    if (isDragging) return;
    try {
      window.localStorage.setItem(STORAGE_PREFIX + key, String(size));
    } catch {
      // localStorage unavailable (private mode, quota) — resizing still works for this session.
    }
  }, [key, size, isDragging]);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!dragStart.current) return;
      const pointerNow = axis === "horizontal" ? e.clientX : e.clientY;
      const delta = pointerNow - dragStart.current.pointer;
      const signedDelta = invert ? -delta : delta;
      const next = Math.min(max, Math.max(min, dragStart.current.size + signedDelta));
      setSize(next);
    },
    [axis, invert, min, max]
  );

  const onPointerUp = useCallback(() => {
    dragStart.current = null;
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (!isDragging) return;
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [isDragging, onPointerMove, onPointerUp]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragStart.current = { pointer: axis === "horizontal" ? e.clientX : e.clientY, size };
      setIsDragging(true);
    },
    [axis, size]
  );

  return { size, isDragging, handleProps: { onPointerDown } };
}
