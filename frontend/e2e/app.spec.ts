import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

function seededJob() {
  return JSON.parse(readFileSync("e2e/.seed.json", "utf8")) as {
    completedTaskId: string;
    completedSourceTitle: string;
  };
}

test("local owner can browse the Library and open a completed clip", async ({ page }) => {
  const job = seededJob();
  await page.goto("/list");
  await expect(page.getByText(job.completedSourceTitle).first()).toBeVisible();

  await page.goto(`/tasks/${job.completedTaskId}`);
  await expect(page.getByRole("link", { name: "Open editor" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy share link" })).toHaveCount(0);

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
});

test("retired pages and payment endpoints are unavailable", async ({ request }) => {
  for (const path of ["/analytics", "/admin", "/share/old", "/invite/old", "/blog", "/faq", "/status", "/terms", "/changelog", "/privacy", "/demo", "/examples", "/affiliate", "/oauth/consent"]) {
    expect((await request.get(path)).status(), path).toBe(404);
  }
  expect((await request.post("/api/billing/checkout")).status()).toBe(404);
  expect((await request.get("/sign-in", { maxRedirects: 0 })).status()).toBe(307);
});
