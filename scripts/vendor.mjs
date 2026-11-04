// Copy pinned third-party browser files from node_modules into static/vendor/.
// Versions are pinned in package.json. Run: npm ci && npm run vendor
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const files = {
  "node_modules/chart.js/dist/chart.umd.min.js": "static/vendor/chart.umd.min.js",
  "node_modules/chart.js/LICENSE.md": "static/vendor/licenses/chart.js.LICENSE.md",
  "node_modules/marked/lib/marked.umd.js": "static/vendor/marked.umd.js",
  "node_modules/marked/LICENSE": "static/vendor/licenses/marked.LICENSE",
  "node_modules/dompurify/dist/purify.min.js": "static/vendor/purify.min.js",
  "node_modules/dompurify/LICENSE": "static/vendor/licenses/dompurify.LICENSE",
  "node_modules/@fontsource/inter/LICENSE": "static/vendor/licenses/inter.LICENSE",
};
// latin + latin-ext (Romanian diacritics: ă â î ș ț)
for (const subset of ["latin", "latin-ext"]) {
  for (const w of [400, 500, 600, 700]) {
    files[`node_modules/@fontsource/inter/files/inter-${subset}-${w}-normal.woff2`] =
      `static/vendor/fonts/inter-${subset}-${w}-normal.woff2`;
  }
}
for (const [from, to] of Object.entries(files)) {
  mkdirSync(dirname(to), { recursive: true });
  copyFileSync(from, to);
  console.log(`${from} -> ${to}`);
}
