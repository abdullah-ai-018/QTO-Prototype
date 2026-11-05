import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

export type PDFDocumentProxy = pdfjsLib.PDFDocumentProxy;

export async function loadPdf(source: string | ArrayBuffer): Promise<PDFDocumentProxy> {
  const loadingTask = pdfjsLib.getDocument(source);
  return loadingTask.promise;
}

export async function renderPageToCanvas(
  doc: PDFDocumentProxy,
  pageIndex: number,
  canvas: HTMLCanvasElement,
  scale: number
) {
  const page = await doc.getPage(pageIndex + 1);
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return { width: viewport.width, height: viewport.height };
  await page.render({ canvasContext: ctx, viewport }).promise;
  return { width: viewport.width, height: viewport.height };
}

export async function renderThumbnail(doc: PDFDocumentProxy, pageIndex: number): Promise<string> {
  const page = await doc.getPage(pageIndex + 1);
  const viewport = page.getViewport({ scale: 0.22 });
  const canvas = document.createElement("canvas");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  const ctx = canvas.getContext("2d");
  if (!ctx) return "";
  await page.render({ canvasContext: ctx, viewport }).promise;
  return canvas.toDataURL();
}
