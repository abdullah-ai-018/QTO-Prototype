import React, { useEffect, useState } from "react";
import { Image as KonvaImage, Rect } from "react-konva";
import { renderPageToCanvas, type PDFDocumentProxy } from "@/lib/pdf";
import { BASE_W, BASE_H } from "@/lib/geometry";

const canvasCache = new Map<string, HTMLCanvasElement>();

function PdfPageLayerComponent({
  doc,
  pageIndex,
  width,
  height,
}: {
  doc: PDFDocumentProxy;
  pageIndex: number;
  width: number;
  height: number;
}) {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const cacheKey = `${pageIndex}`;

    if (canvasCache.has(cacheKey)) {
      setCanvas(canvasCache.get(cacheKey)!);
      return;
    }

    const c = document.createElement("canvas");
    renderPageToCanvas(doc, pageIndex, c, 2).then(() => {
      if (!cancelled) {
        canvasCache.set(cacheKey, c);
        setCanvas(c);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [doc, pageIndex]);

  if (!canvas) {
    return <Rect x={0} y={0} width={width} height={height} fill="#0e1116" />;
  }

  return <KonvaImage image={canvas} x={0} y={0} width={width} height={height} listening={false} />;
}

export default React.memo(PdfPageLayerComponent);
