import { describe, expect, it } from "vitest";

import { catalogKey, intlLocale, defaultLocale, locales } from "./config";

it("ships English as the only interface locale", () => {
  expect(locales).toEqual(["en"]);
  expect(defaultLocale).toBe("en");
});

describe("locale helpers", () => {
  it("maps app locales onto BCP 47 tags", () => {
    expect(intlLocale("zh")).toBe("zh-Hans");
    expect(intlLocale("pt")).toBe("pt-BR");
    expect(intlLocale("de")).toBe("de");
    expect(intlLocale("id")).toBe("id");
  });

  it("builds flat catalog keys from paths", () => {
    expect(catalogKey("/blog/self-host-supoclip-docker")).toBe("blog_self_host_supoclip_docker");
  });
});
