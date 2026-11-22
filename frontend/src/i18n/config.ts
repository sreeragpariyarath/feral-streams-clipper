export const locales = ["en"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

/** Top-level message files under `frontend/messages/<locale>/`. */
export const NAMESPACES = [
  "common",
  "metadata",
  "language",
  "shell",
  "auth",
  "settings",
  "team",
  "billing",
  "home",
  "library",
  "task", "tours",
  "editor",
  "social",
  "analytics",
  "marketing",
  "seo",
  "blog",
  "changelog",
  "admin",
  "affiliate",
  "examples",
  "status",
  "share",
  "legal",
] as const;

export type Namespace = (typeof NAMESPACES)[number];

/** BCP 47 tag used for `lang`, dates, and `Intl` formatters. */
export function intlLocale(locale: string): string {
  if (locale === "zh") return "zh-Hans";
  if (locale === "pt") return "pt-BR";
  return locale;
}

/** Flat message-catalog key for a path such as `/blog/self-host`. */
export function catalogKey(href: string): string {
  return href
    .replace(/^\//, "")
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_|_$/g, "")
    .toLowerCase();
}
