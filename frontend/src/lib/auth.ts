import { betterAuth } from "better-auth";
import { prismaAdapter } from "better-auth/adapters/prisma";
import prisma from "@/lib/prisma";
import { nextCookies } from "better-auth/next-js";
import { getAuthTrustedOrigins } from "@/lib/auth-origins";
import { prepareAccountDeletion } from "@/server/account-deletion";
import { fetchBackend } from "@/server/backend-api";

const disableSignUp = ["1", "true", "yes"].includes(
  (process.env.DISABLE_SIGN_UP ?? "").toLowerCase()
);

async function sendPasswordResetEmail(userId: string, url: string) {
  const response = await fetchBackend("/account/password-reset-email", {
    method: "POST",
    userId,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(
      `Backend password reset email failed with ${response.status}: ${detail || "unknown error"}`
    );
  }
}

const trustedOrigins = getAuthTrustedOrigins({
  NEXT_PUBLIC_APP_URL: process.env.NEXT_PUBLIC_APP_URL,
  BETTER_AUTH_URL: process.env.BETTER_AUTH_URL,
  BETTER_AUTH_TRUSTED_ORIGINS: process.env.BETTER_AUTH_TRUSTED_ORIGINS,
  NEXT_PUBLIC_SELF_HOST: process.env.NEXT_PUBLIC_SELF_HOST,
});

const standardAuth = betterAuth({
  database: prismaAdapter(prisma, {
    provider: "postgresql",
  }),
  user: {
    deleteUser: {
      enabled: true,
      beforeDelete: async (user) => {
        await prepareAccountDeletion(user.id);
      },
    },
    additionalFields: {
      is_admin: {
        type: "boolean",
        input: false,
      },
    },
  },
  trustedOrigins,
  // Over HTTP only; server code can still call auth.api.verifyPassword. A public
  // verify-password would let a stolen session guess the password at the generic
  // rate limit, around the limits of the email change flow, and change-email
  // would skip that flow's codes if it were ever switched on.
  disabledPaths: ["/verify-password", "/change-email"],
  emailVerification: {
    sendOnSignUp: false,
    sendOnSignIn: false,
    expiresIn: 3600,
    sendVerificationEmail: async ({ user, url }) => {
      const response = await fetchBackend("/account/verification-email", {
        method: "POST",
        userId: user.id,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
        cache: "no-store",
      });
      if (!response.ok) {
        // Do not log the verification URL or token.
        throw new Error(`Verification email delivery failed (${response.status})`);
      }
    },
  },
  emailAndPassword: {
    enabled: true,
    disableSignUp,
    revokeSessionsOnPasswordReset: true,
    sendResetPassword: async ({ user, url }) => {
      // Not awaited so response timing doesn't reveal whether an account exists.
      void sendPasswordResetEmail(user.id, url).catch((error) => {
        console.error("Failed to send password reset email", error);
      });
    },
  },
  plugins: [
    nextCookies(), // Enable Next.js cookie handling
  ],
});

export type Session = typeof standardAuth.$Infer.Session;

export const auth = {
  ...standardAuth,
  api: {
    ...standardAuth.api,
    async getSession(...args: Parameters<typeof standardAuth.api.getSession>) {
      const owner = process.env.SUPOCLIP_LOCAL_OWNER_ID;
      if (!owner) return standardAuth.api.getSession(...args);
      const origin = new URL(process.env.SUPOCLIP_LOCAL_ORIGIN ?? "http://localhost:3107");
      const incoming = new Headers(args[0]?.headers);
      if (!["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname) ||
          incoming.get("host") !== origin.host ||
          incoming.get("sec-fetch-site") === "cross-site" ||
          (incoming.has("origin") && incoming.get("origin") !== origin.origin)) {
        return null;
      }
      const user = await prisma.user.findUnique({
        where: { id: owner },
        select: { id: true, name: true, email: true, emailVerified: true,
          image: true, createdAt: true, updatedAt: true },
      });
      if (!user) return null;
      return {
        user: { ...user, is_admin: false },
        session: {
          id: "local-owner", userId: user.id, token: "",
          expiresAt: new Date(Date.now() + 86400000),
          createdAt: user.createdAt, updatedAt: user.updatedAt,
        },
      } satisfies Session;
    },
  },
};
