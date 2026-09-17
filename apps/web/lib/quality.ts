import type { ImageQueueItem, QualityReason, QualityStatus, QualitySummary } from "./types";

export interface ImageSignals {
  mean: number;
  contrast: number;
  detail: number;
  megapixels: number;
}

export function classifyQuality(signals: ImageSignals): QualitySummary {
  const reasons: QualityReason[] = [];
  if (signals.mean < 38) reasons.push({ code: "DARK", message: "Image may be underexposed." });
  if (signals.mean > 224) reasons.push({ code: "BRIGHT", message: "Image may be overexposed." });
  if (signals.contrast < 24) reasons.push({ code: "LOW_CONTRAST", message: "Label text has low contrast." });
  if (signals.detail < 21) reasons.push({ code: "POSSIBLE_BLUR", message: "Fine label detail may be blurred." });
  if (signals.megapixels < 0.7) reasons.push({ code: "LOW_RESOLUTION", message: "Capture resolution is below 0.7 MP." });

  let status: QualityStatus = "GOOD";
  if (reasons.length >= 2 || signals.megapixels < 0.25) status = "POOR";
  else if (reasons.length === 1) status = "FAIR";

  const penalties = reasons.reduce((sum, reason) => {
    if (reason.code === "LOW_RESOLUTION") return sum + 0.25;
    if (reason.code === "POSSIBLE_BLUR") return sum + 0.22;
    return sum + 0.16;
  }, 0);

  return {
    status,
    score: Number(Math.max(0.05, Math.min(1, 0.97 - penalties)).toFixed(2)),
    policy_version: "QUALITY_BROWSER_V1",
    reasons,
  };
}

export async function measureImage(file: File): Promise<Omit<ImageQueueItem, "id" | "file" | "preview">> {
  const bitmap = await createImageBitmap(file);
  const sampleMax = 420;
  const scale = Math.min(1, sampleMax / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("Canvas image analysis is unavailable in this browser.");
  context.drawImage(bitmap, 0, 0, width, height);
  const pixels = context.getImageData(0, 0, width, height).data;
  const lumas = new Float32Array(width * height);
  let sum = 0;
  let sumSq = 0;
  let edge = 0;
  for (let i = 0, p = 0; i < pixels.length; i += 4, p += 1) {
    const luminance = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
    lumas[p] = luminance;
    sum += luminance;
    sumSq += luminance * luminance;
  }
  for (let y = 1; y < height; y += 2) {
    for (let x = 1; x < width; x += 2) {
      const position = y * width + x;
      edge += Math.abs(lumas[position] - lumas[position - 1]) + Math.abs(lumas[position] - lumas[position - width]);
    }
  }
  const samples = width * height;
  const mean = sum / samples;
  const contrast = Math.sqrt(Math.max(0, sumSq / samples - mean * mean));
  const edgeSamples = Math.max(1, Math.floor((width - 1) / 2) * Math.floor((height - 1) / 2));
  const detail = edge / edgeSamples;
  const originalWidth = bitmap.width;
  const originalHeight = bitmap.height;
  bitmap.close();
  const megapixels = (originalWidth * originalHeight) / 1_000_000;
  return {
    width: originalWidth,
    height: originalHeight,
    megapixels,
    quality: classifyQuality({ mean, contrast, detail, megapixels }),
  };
}

export function aggregateQuality(items: ImageQueueItem[]): QualitySummary {
  if (!items.length) {
    return {
      status: "FAIR",
      score: 0.5,
      policy_version: "QUALITY_BROWSER_V1",
      reasons: [{ code: "NO_IMAGE", message: "No evidence image has been added." }],
    };
  }
  const rank: Record<QualityStatus, number> = { GOOD: 0, FAIR: 1, POOR: 2 };
  const worst = [...items].sort((a, b) => rank[b.quality.status] - rank[a.quality.status])[0].quality.status;
  const score = items.reduce((total, item) => total + item.quality.score, 0) / items.length;
  const reasons = items.flatMap((item, index) =>
    item.quality.reasons.map((reason) => ({ ...reason, message: `Image ${index + 1}: ${reason.message}` })),
  );
  return {
    status: worst,
    score: Number(score.toFixed(2)),
    policy_version: "QUALITY_BROWSER_V1",
    reasons,
  };
}

export async function compressImage(file: File, maxDimension = 1600, quality = 0.82): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("Canvas compression is unavailable in this browser.");
  }
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  if (!blob) throw new Error("Could not compress the selected image.");
  return blob;
}

export async function blobToBase64(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}
