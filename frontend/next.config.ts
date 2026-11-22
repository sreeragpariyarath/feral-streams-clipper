import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { withPostHogConfig } from "@posthog/nextjs-config";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const isPostHogEnabled = Boolean(process.env.NEXT_PUBLIC_POSTHOG_KEY?.trim());
const posthogHost = (process.env.NEXT_PUBLIC_POSTHOG_HOST?.trim() || "https://eu.i.posthog.com").replace(/\/$/, "");
// PostHog Cloud serves the SDK bundles from a separate assets host.
const posthogAssetsHost = posthogHost.replace(/^https:\/\/(us|eu)\.i\.posthog\.com$/, "https://$1-assets.i.posthog.com");

// Same-origin reverse proxy so ad blockers don't drop analytics, replays, and error reports.
const posthogRewrites = isPostHogEnabled
  ? [
      { source: "/ingest/static/:path*", destination: `${posthogAssetsHost}/static/:path*` },
      { source: "/ingest/array/:path*", destination: `${posthogAssetsHost}/array/:path*` },
      { source: "/ingest/:path*", destination: `${posthogHost}/:path*` },
    ]
  : [];

const nextConfig: NextConfig = {
  env: {
    SUPOCLIP_LOCAL_MODE: process.env.SUPOCLIP_LOCAL_OWNER_ID ? "true" : "false",
    SUPOCLIP_LOCAL_ORIGIN: process.env.SUPOCLIP_LOCAL_ORIGIN ?? "http://localhost:3107",
  },
  distDir: process.env.NEXT_BUILD_DIR || ".next",
  output: 'standalone',
  // Keep canonical tags in the initial <head>, including for Googlebot.
  htmlLimitedBots: /.*/,
  // PostHog's API paths end in a slash (e.g. /e/); don't redirect them.
  skipTrailingSlashRedirect: isPostHogEnabled,
  typescript: {
    ignoreBuildErrors: false,
  },
  async redirects() {
    if (!process.env.SUPOCLIP_LOCAL_OWNER_ID) return [];
    return ["/sign-in", "/sign-up", "/forgot-password", "/reset-password"].map((source) => ({
      source, destination: "/", permanent: false,
    }));
  },
  async rewrites() {
    return {
      beforeFiles: process.env.SUPOCLIP_LOCAL_OWNER_ID ? [
        "/api/billing/:path*",
        "/api/teams/:teamId/billing/:path*",
        "/api/affiliates/offer",
      ].map((source) => ({ source, destination: "/api/local-billing-unavailable" })) : [],
      afterFiles: [
      {
        source: "/js/script.js",
        destination: "https://datafa.st/js/script.js",
      },
      {
        source: "/api/events",
        destination: "https://datafa.st/api/events",
      },
      ...posthogRewrites,
      ],
    };
  },
};

const intlConfig = withNextIntl(nextConfig);

// Source maps upload only when a build has PostHog credentials; other builds are unchanged.
const posthogPersonalApiKey = process.env.POSTHOG_PERSONAL_API_KEY?.trim();
const posthogProjectId = process.env.POSTHOG_PROJECT_ID?.trim();

export default posthogPersonalApiKey && posthogProjectId
  ? withPostHogConfig(intlConfig, {
      personalApiKey: posthogPersonalApiKey,
      projectId: posthogProjectId,
      host: posthogHost.replace(/^https:\/\/(us|eu)\.i\.posthog\.com$/, "https://$1.posthog.com"),
      sourcemaps: {
        enabled: true,
        releaseName: "supoclip-web",
        releaseVersion: process.env.POSTHOG_RELEASE_VERSION?.trim() || undefined,
        deleteAfterUpload: true,
      },
    })
  : intlConfig;
