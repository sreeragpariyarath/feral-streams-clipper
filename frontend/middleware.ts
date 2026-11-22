import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_FILE = /\.(.*)$/;

export function middleware(request: NextRequest) {
  if (process.env.SUPOCLIP_LOCAL_MODE === "true") {
    const origin = process.env.SUPOCLIP_LOCAL_ORIGIN ?? "http://localhost:3107";
    const requestOrigin = request.headers.get("origin");
    if (request.headers.get("host") !== new URL(origin).host ||
        (requestOrigin && requestOrigin !== origin) ||
        request.headers.get("sec-fetch-site") === "cross-site") {
      return new NextResponse(null, { status: 403 });
    }
    const { pathname } = request.nextUrl;
    if (["/sign-in", "/sign-up", "/forgot-password", "/reset-password"].includes(pathname)) {
      return NextResponse.redirect(new URL("/", origin));
    }
    if (pathname.startsWith("/oauth/") || pathname.startsWith("/invite/") ||
        pathname.startsWith("/api/account/email-change")) {
      return new NextResponse(null, { status: 404 });
    }
  }
  const isLandingOnlyModeEnabled =
    process.env.NEXT_PUBLIC_LANDING_ONLY_MODE === "true";

  if (!isLandingOnlyModeEnabled) {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;

  if (
    pathname === "/" ||
    pathname === "/status" ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api/billing/webhook") ||
    pathname.startsWith("/ingest/") ||
    // Opt-outs (including mailbox one-click POSTs) must work in every mode.
    pathname === "/email/product-updates/unsubscribe" ||
    PUBLIC_FILE.test(pathname)
  ) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api")) {
    return NextResponse.json(
      { error: "SupoClip is in landing-page-only mode." },
      { status: 503 }
    );
  }

  const url = request.nextUrl.clone();
  url.pathname = "/";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: "/:path*",
};
