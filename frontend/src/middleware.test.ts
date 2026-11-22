// @vitest-environment node
import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "../middleware";

afterEach(() => vi.unstubAllEnvs());

it("keeps product-update opt-outs reachable in landing-only mode", () => {
  vi.stubEnv("NEXT_PUBLIC_LANDING_ONLY_MODE", "true");
  for (const method of ["GET", "POST"]) {
    const response = middleware(new NextRequest(
      "https://app.example.com/email/product-updates/unsubscribe?token=v1.signed", { method },
    ));
    expect(response.headers.get("x-middleware-next")).toBe("1");
  }
  const blocked = middleware(new NextRequest("https://app.example.com/dashboard"));
  expect(blocked.status).toBe(307);
});

it("allows the localhost workspace and redirects sign-in in local mode", () => {
  vi.stubEnv("SUPOCLIP_LOCAL_MODE", "true");
  const local = { host: "localhost:3107" };
  expect(middleware(new NextRequest("http://localhost:3107/list", { headers: local }))
    .headers.get("x-middleware-next")).toBe("1");
  expect(middleware(new NextRequest("http://localhost:3107/sign-in", { headers: local }))
    .headers.get("location")).toBe("http://localhost:3107/");
  expect(middleware(new NextRequest("http://localhost:3107/api/tasks", {
    headers: { ...local, origin: "https://example.com" },
  })).status).toBe(403);
  expect(middleware(new NextRequest("http://example.com/api/tasks", {
    headers: { host: "example.com" },
  })).status).toBe(403);
});
