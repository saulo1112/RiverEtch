import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The cases panel's thumbnail of the reference case, rendered by `npm run capture:thumbnail`
// (scripts/capture-case-thumbnail.mjs). Until both sizes exist the card draws the reach's outline
// and requests no image, so it never shows a broken image. Checked when Vite starts.
const caseThumbnail = ["magdalena-reference.webp", "magdalena-reference-960.webp"].every((name) =>
  existsSync(fileURLToPath(new URL(`./public/cases/${name}`, import.meta.url))),
);

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: { __CASE_THUMBNAIL__: JSON.stringify(caseThumbnail) },
});
