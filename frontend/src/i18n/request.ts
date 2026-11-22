import { getRequestConfig } from "next-intl/server";

import { defaultLocale } from "./config";
import { loadMessages } from "./load-messages";

export default getRequestConfig(async () => ({
  locale: defaultLocale,
  messages: await loadMessages(defaultLocale),
}));
