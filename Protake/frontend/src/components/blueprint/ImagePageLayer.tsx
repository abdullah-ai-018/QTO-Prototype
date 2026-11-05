import React, { useEffect, useState } from "react";
import { Image as KonvaImage, Rect } from "react-konva";

/**
 * Renders a directly-uploaded raster blueprint (PNG/JPG/WEBP/TIFF).
 *
 * pdf.js cannot open an image — it throws InvalidPDFException — so image
 * uploads have no PDFDocumentProxy and must be drawn straight from the
 * object URL instead of going through PdfPageLayer.
 */
function ImagePageLayerComponent({
  src,
  width,
  height,
}: {
  src: string;
  width: number;
  height: number;
}) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const img = new window.Image();
    img.onload = () => {
      if (!cancelled) setImage(img);
    };
    img.onerror = () => {
      if (!cancelled) setImage(null);
    };
    img.src = src;
    return () => {
      cancelled = true;
    };
  }, [src]);

  if (!image) {
    return <Rect x={0} y={0} width={width} height={height} fill="#0e1116" />;
  }

  return <KonvaImage image={image} x={0} y={0} width={width} height={height} listening={false} />;
}

export default React.memo(ImagePageLayerComponent);
