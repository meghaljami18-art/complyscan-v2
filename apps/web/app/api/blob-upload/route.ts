import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

export const runtime = "nodejs";

const WRITE_ROLES = new Set(["ADMIN", "LEGAL_REVIEWER", "COMPLIANCE_ANALYST"]);

function demoRole(authorization: string): string | null {
  if (process.env.APP_ENV === "production" || !authorization.startsWith("Bearer demo:")) return null;
  const role = authorization.split(":").at(-1) || "";
  return WRITE_ROLES.has(role) ? role : null;
}

async function authorize(request: Request): Promise<void> {
  const authorization = request.headers.get("authorization") || "";
  if (demoRole(authorization)) return;
  if (!authorization.startsWith("Bearer ")) throw new Error("Authentication is required.");

  const configuredBase = process.env.API_INTERNAL_BASE_URL?.replace(/\/$/, "");
  const origin = configuredBase || new URL(request.url).origin;
  const response = await fetch(`${origin}/api/me`, {
    headers: { Authorization: authorization, Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Upload authorization was rejected.");
  const body = (await response.json()) as { user?: { role?: string } };
  if (!body.user?.role || !WRITE_ROLES.has(body.user.role)) throw new Error("This role cannot upload evidence.");
}

export async function POST(request: Request): Promise<Response> {
  try {
    await authorize(request);
    const body = (await request.json()) as HandleUploadBody;
    const result = await handleUpload({
      request,
      body,
      onBeforeGenerateToken: async (pathname) => {
        if (!pathname.startsWith("complyscan/") || pathname.includes("..")) {
          throw new Error("Unsafe evidence pathname.");
        }
        return {
          allowedContentTypes: ["image/jpeg", "image/png", "image/webp"],
          maximumSizeInBytes: 15 * 1024 * 1024,
          validUntil: Date.now() + 10 * 60 * 1000,
          addRandomSuffix: true,
          allowOverwrite: false,
          tokenPayload: JSON.stringify({ purpose: "complyscan-evidence" }),
        };
      },
      onUploadCompleted: async () => {
        // FastAPI registers immutable metadata after the client receives the Blob receipt.
      },
    });
    return Response.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Upload authorization failed.";
    return Response.json({ error: { code: "UPLOAD_AUTHORIZATION_FAILED", message } }, { status: 400 });
  }
}
