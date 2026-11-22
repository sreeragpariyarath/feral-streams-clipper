"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  Film, PanelLeftClose, PanelLeftOpen, Plus, KeyRound, LayoutGrid, Send, SlidersHorizontal, Wand2,
} from "lucide-react";
import { useSession } from "@/lib/auth-client";
import { useSocialAccess } from "@/hooks/use-social-access";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAppTheme } from "@/components/theme-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { FeatureTourHost } from "@/components/feature-tour";
import type { Workflow } from "@/lib/workflows";

// `mobile: false` keeps an item out of the five-slot mobile tab bar.
// `social: true` items only show when social publishing is enabled for the user.
type NavItem = { href: string; labelKey: "create" | "library" | "social" | "analytics" | "agents" | "settings"; icon: typeof Film; match: (path: string) => boolean; mobile?: boolean; social?: boolean };

const NAV: NavItem[] = [
  { href: "/", labelKey: "create", icon: Wand2, match: (p) => p === "/" },
  { href: "/list", labelKey: "library", icon: LayoutGrid, match: (p) => p.startsWith("/list") || p.startsWith("/tasks") },
  { href: "/settings/social", labelKey: "social", icon: Send, match: (p) => p.startsWith("/settings/social"), social: true },
  { href: "/settings/api-keys", labelKey: "agents", icon: KeyRound, match: (p) => p.startsWith("/settings/api-keys"), mobile: false },
  { href: "/settings", labelKey: "settings", icon: SlidersHorizontal, match: (p) => p === "/settings" },
];

/** What the create screen tells the tour host; other pages need nothing. */
export type ShellTour = {
  /** The user is doing something: don't start a tour, and leave one that's showing. */
  busy: boolean;
  onWorkflow?: (workflow: Workflow) => void;
  onEnd?: () => void;
  /** Open a section of the composer's settings menu for a step that points into it. */
  onSettingsSection?: (id: string) => void;
};

const ShellTourContext = createContext<(tour: ShellTour | undefined) => void>(() => {});

/** The create screen registers its tour with the shared shell; other pages register nothing. */
export function useShellTour(tour: ShellTour) {
  const setTour = useContext(ShellTourContext);
  const { busy, onWorkflow, onEnd, onSettingsSection } = tour;
  useEffect(() => {
    setTour({ busy, onWorkflow, onEnd, onSettingsSection });
    return () => setTour(undefined);
  }, [setTour, busy, onWorkflow, onEnd, onSettingsSection]);
}

/** Signed-in application chrome: sidebar on desktop, tab bar on mobile, ⌘K palette and feature tours everywhere. */
export function AppShell({ children, tour: tourProp }: { children: React.ReactNode; /** Set by the create screen, the only page a tour starts on. */ tour?: ShellTour }) {
  const t = useTranslations("shell");
  const [registeredTour, setRegisteredTour] = useState<ShellTour | undefined>(undefined);
  const tour = tourProp ?? registeredTour;
  const { data: session } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  // The editor is a full-screen workspace with its own back button: no app
  // chrome there. Elements stay in place (hidden) so children keep their position.
  const immersive = /^\/tasks\/[^/]+\/edit/.test(pathname);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    try { setExpanded(localStorage.getItem("sidebar-expanded") === "1"); } catch {}
  }, []);
  const toggleExpanded = () => setExpanded((open) => {
    try { localStorage.setItem("sidebar-expanded", open ? "0" : "1"); } catch {}
    return !open;
  });
  const compact = !expanded;
  const navigate = useCallback((path: string) => router.push(path), [router]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target?.closest("input, textarea, select, [contenteditable=true], [role=dialog]");
      if (!typing && !event.metaKey && !event.ctrlKey && !event.altKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        router.push("/");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  // Children must keep the same tree position whether or not the session has
  // loaded — otherwise the page remounts and re-runs its initial fetches.
  const user = session?.user;
  useAppTheme(Boolean(user));
  const socialAccess = useSocialAccess(Boolean(user));
  const labeled = NAV.map((item) => ({ ...item, label: t(`nav.${item.labelKey}`) }));
  const nav = labeled.filter((item) => !item.social || socialAccess === true);
  const mobileNav = nav.filter((item) => item.mobile !== false);
  const items = nav;

  return (
    <ShellTourContext.Provider value={setRegisteredTour}>
    <div data-app-shell={user ? "" : undefined} className={cn(user && "flex min-h-dvh bg-canvas")}>
      {user ? <aside
        className={cn(
          "sticky top-3 m-3 hidden h-[calc(100dvh-1.5rem)] shrink-0 flex-col rounded-3xl bg-sidebar px-3 pb-14 pt-4 transition-[width] duration-200",
          compact ? "w-[72px] items-center" : "w-60",
          !immersive && "md:flex",
        )}
      >
        <div className={cn("flex w-full items-center", compact ? "flex-col gap-3" : "justify-between pl-1")}>
          <Link href="/" aria-label="Feral Streams" className="flex size-11 items-center justify-center rounded-full bg-sidebar-accent ring-1 ring-white/5">
            <Image src="/logo.png" alt="Feral Streams" width={32} height={32} className="size-8" priority />
          </Link>
          <button type="button" onClick={toggleExpanded} aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"} className="flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground">
            {expanded ? <PanelLeftClose className="size-[18px]" /> : <PanelLeftOpen className="size-[18px]" />}
          </button>
        </div>

        <Link
          href="/"
          aria-label={t("nav.newGeneration")}
          className={cn(
            "group mt-6 box-border flex h-12 min-w-0 items-center rounded-2xl bg-primary text-sm font-semibold text-primary-foreground shadow-[0_6px_20px_-8px] shadow-primary/60 transition hover:-translate-y-px hover:shadow-primary/80",
            compact ? "w-12 justify-center" : "w-full gap-3 px-2.5",
          )}
        >
          <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-black/10 transition-transform group-hover:rotate-90">
            <Plus className="size-[18px]" strokeWidth={2.5} />
          </span>
          {!compact && <>
            <span className="min-w-0 flex-1 truncate text-left">{t("nav.newGeneration")}</span>
            <kbd className="shrink-0 rounded-md border border-black/15 px-1.5 py-0.5 font-sans text-[10px] font-semibold leading-none opacity-70">N</kbd>
          </>}
        </Link>

        <nav aria-label={t("search.mainNav")} className={cn("mt-7 flex w-full flex-col gap-1", compact && "items-center")}>
          {!compact && <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/70">Menu</p>}
          {items.filter((item) => item.labelKey !== "settings" && item.labelKey !== "agents").map((item) => (
            <SidebarLink key={item.href} compact={compact} href={item.href} label={item.label} active={item.match(pathname)} tour={`nav-${item.labelKey}`}>
              <item.icon className="size-[18px]" />
            </SidebarLink>
          ))}

          {!compact && <p className="mb-1 mt-6 px-3 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground/70">More</p>}
          {compact && <div className="my-2 h-px w-8 bg-border" />}
          {items.filter((item) => item.labelKey === "agents" || item.labelKey === "settings").map((item) => (
            <SidebarLink key={item.href} compact={compact} href={item.href} label={item.label} active={item.match(pathname)} tour={`nav-${item.labelKey}`}>
              <item.icon className="size-[18px]" />
            </SidebarLink>
          ))}
        </nav>

        <div className={cn("mt-auto flex w-full items-center", compact ? "justify-center" : "justify-between rounded-2xl bg-sidebar-accent/60 py-1.5 pl-3 pr-1.5")}>
          {!compact && <span className="text-xs font-medium text-muted-foreground">Theme</span>}
          <ThemeToggle tooltipSide="right" className="flex size-9 items-center justify-center rounded-xl bg-sidebar-accent text-foreground hover:bg-sidebar-accent/70 [&_svg]:size-[18px]" />
        </div>
      </aside> : null}

      <div className={cn(user && "flex min-w-0 flex-1 flex-col", user && !immersive && "pb-[calc(4rem+env(safe-area-inset-bottom))] md:pb-0")}>
        {user && !immersive ? <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/80 px-4 backdrop-blur md:hidden">
          <Link href="/" className="flex items-center gap-2 font-display text-lg font-bold tracking-tight">
            <Image src="/logo.png" alt="" width={22} height={22} className="size-[22px]" />Feral Streams
          </Link>
          <div className="flex items-center gap-1">
            <ThemeToggle tooltipSide="bottom" className="rounded-lg p-2 hover:bg-accent [&_svg]:size-5" />
          </div>
        </header> : null}
        {children}
      </div>

      {user && !immersive ? <nav aria-label={t("search.mobileNav")} style={{ gridTemplateColumns: `repeat(${mobileNav.length}, minmax(0, 1fr))` }} className="fixed inset-x-0 bottom-0 z-40 grid border-t bg-background/90 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        {mobileNav.map((item) => {
          const active = item.match(pathname);
          return (
            <Link key={item.href} href={item.href} data-tour={`nav-${item.labelKey}`} aria-current={active ? "page" : undefined}
              className={cn("flex h-16 flex-col items-center justify-center gap-1 text-[11px] font-medium", active ? "text-foreground" : "text-muted-foreground")}>
              <item.icon className={cn("size-5", active && "text-brand")} />{item.label}
            </Link>
          );
        })}
      </nav> : null}

      <FeatureTourHost
        enabled={Boolean(user) && !immersive}
        pathname={pathname}
        navigate={navigate}
        canStart={tour !== undefined && pathname === "/"}
        busy={tour?.busy}
        onWorkflow={tour?.onWorkflow}
        onEnd={tour?.onEnd}
        onSettingsSection={tour?.onSettingsSection}
      />
    </div>
    </ShellTourContext.Provider>
  );
}

function SidebarLink({ href, label, active, compact, shortcut, className, tour, children }: {
  href: string; label: string; active?: boolean; compact: boolean; shortcut?: string; className?: string; /** `data-tour` target for the welcome tour. */ tour?: string; children: React.ReactNode;
}) {
  const link = (
    <Link
      data-tour={tour}
      href={href}
      aria-current={active ? "page" : undefined}
      aria-label={compact ? label : undefined}
      className={cn(
        "relative flex h-11 w-full items-center gap-3 rounded-2xl text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        compact ? "justify-center" : "px-3",
        active && "bg-sidebar-accent [&_svg]:text-primary",
        active ? "text-foreground before:absolute before:-left-[14px] before:top-2.5 before:h-6 before:w-1 before:rounded-r-full before:bg-primary" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
        className,
      )}
    >
      {children}
      {!compact && <span className="flex-1">{label}</span>}
      {!compact && shortcut && <span className="text-[11px] opacity-60">{shortcut}</span>}
    </Link>
  );
  if (!compact) return link;
  return <Tooltip><TooltipTrigger asChild>{link}</TooltipTrigger><TooltipContent side="right">{label}</TooltipContent></Tooltip>;
}
