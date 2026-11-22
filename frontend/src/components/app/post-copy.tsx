"use client";

import { useEffect, useState } from "react";
import { Check, Copy, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type PostCopyResult = {
  instagram: { caption: string; hashtags: string[] };
  youtube: { title: string; description: string; hashtags: string[] };
};

type Platform = "instagram" | "youtube";

/** Instagram caption and YouTube title and description for one clip, written from its own transcript. */
export function PostCopy({ taskId, clipId }: { taskId: string; clipId: string }) {
  const [copy, setCopy] = useState<PostCopyResult | null>(null);
  const [platform, setPlatform] = useState<Platform>("instagram");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  // Another clip opened in the same dialog: forget the previous clip's copy.
  useEffect(() => {
    setCopy(null);
    setError(null);
    setCopied(null);
  }, [clipId]);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/tasks/${taskId}/clips/${clipId}/post-copy`, { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || body?.error || "Couldn't write the copy. Try again.");
      setCopy(body as PostCopyResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't write the copy. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function copyText(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      window.setTimeout(() => setCopied((current) => (current === key ? null : current)), 1500);
    } catch {
      setError("Couldn't copy. Select the text and copy it.");
    }
  }

  const instagramText = copy ? `${copy.instagram.caption}\n\n${copy.instagram.hashtags.join(" ")}`.trim() : "";
  const youtubeDescription = copy ? copy.youtube.description : "";

  return (
    <section className="rounded-xl border p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Post copy</h3>
          <p className="text-xs text-muted-foreground">Caption and description for Instagram and YouTube, from this clip.</p>
        </div>
        <Button size="sm" variant={copy ? "outline" : "default"} onClick={generate} disabled={loading}>
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {copy ? "Rewrite" : "Generate"}
        </Button>
      </div>

      {error && <p className="mt-3 text-xs text-destructive" role="alert">{error}</p>}

      {copy && (
        <div className="mt-4 space-y-3">
          <div className="inline-flex rounded-lg bg-muted p-0.5 text-xs font-medium" role="tablist">
            {(["instagram", "youtube"] as const).map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={platform === item}
                onClick={() => setPlatform(item)}
                className={cn("rounded-md px-3 py-1.5 transition-colors", platform === item ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}
              >
                {item === "instagram" ? "Instagram" : "YouTube"}
              </button>
            ))}
          </div>

          {platform === "instagram" ? (
            <CopyBlock label="Caption" text={instagramText} copied={copied === "instagram"} onCopy={() => copyText("instagram", instagramText)} />
          ) : (
            <>
              <CopyBlock label="Title" text={copy.youtube.title} copied={copied === "title"} onCopy={() => copyText("title", copy.youtube.title)} />
              <CopyBlock label="Description" text={youtubeDescription} copied={copied === "description"} onCopy={() => copyText("description", youtubeDescription)} />
            </>
          )}
        </div>
      )}
    </section>
  );
}

function CopyBlock({ label, text, copied, onCopy }: { label: string; text: string; copied: boolean; onCopy: () => void }) {
  return (
    <div className="rounded-lg bg-muted/60 p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        <Button size="sm" variant="ghost" className="h-7 gap-1.5 px-2 text-xs" onClick={onCopy}>
          {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
    </div>
  );
}
