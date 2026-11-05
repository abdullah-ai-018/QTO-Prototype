import { createContext, useContext } from "react";
import { BASE_W, BASE_H } from "@/lib/geometry";

/**
 * The pixel size of the drawing surface that normalized [0,1] coordinates
 * map onto.
 *
 * Detections arrive normalized against the *rasterized page image*, so the
 * surface has to carry that page's aspect ratio or every shape is stretched:
 * a square sheet forced into the old fixed 1600x1000 box came out 1.6x wider
 * than tall, which distorted every room polygon and every measurement drawn
 * over it.
 *
 * Width stays fixed at BASE_W and height is derived from the page, so zoom
 * and pan behaviour are unchanged.
 */
export interface StageSize {
  width: number;
  height: number;
}

export const DEFAULT_STAGE_SIZE: StageSize = { width: BASE_W, height: BASE_H };

export const StageSizeContext = createContext<StageSize>(DEFAULT_STAGE_SIZE);

export function useStageSize(): StageSize {
  return useContext(StageSizeContext);
}

/** Derive the drawing surface from a page's pixel dimensions. */
export function stageSizeForPage(widthPx?: number, heightPx?: number): StageSize {
  if (!widthPx || !heightPx || widthPx <= 0 || heightPx <= 0) {
    return DEFAULT_STAGE_SIZE;
  }
  return { width: BASE_W, height: Math.round((BASE_W * heightPx) / widthPx) };
}
