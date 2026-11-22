import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

const standard = toNextJsHandler(auth.handler);

export async function GET(request: Request) {
  if (!process.env.SUPOCLIP_LOCAL_OWNER_ID) return standard.GET(request);
  if (new URL(request.url).pathname !== "/api/auth/get-session") {
    return new Response(null, { status: 404 });
  }
  const session = await auth.api.getSession({ headers: request.headers });
  if (!session) return Response.json(null, { headers: { "Cache-Control": "no-store" } });
  const { id, name, email, emailVerified, image, createdAt, updatedAt, is_admin } = session.user;
  return Response.json({
    user: { id, name, email, emailVerified, image, createdAt, updatedAt, is_admin },
    session: session.session,
  }, { headers: { "Cache-Control": "no-store" } });
}

export function POST(request: Request) {
  if (process.env.SUPOCLIP_LOCAL_OWNER_ID) return new Response(null, { status: 404 });
  return standard.POST(request);
}
