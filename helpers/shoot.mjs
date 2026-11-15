// Render HTML pages to PNG in one Chrome session.
// stdin: {"jobs":[{"url","out","width","height","scale","transparent"}]}
// One browser launch covers every overlay and static in a render, which is
// what keeps text changes fast.
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const { jobs } = JSON.parse(fs.readFileSync(0, 'utf8'));
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const groups = new Map();
for (const j of jobs) {
  const k = `${j.width}x${j.height}@${j.scale}`;
  if (!groups.has(k)) groups.set(k, []);
  groups.get(k).push(j);
}
let failed = 0;
for (const js of groups.values()) {
  const { width, height, scale } = js[0];
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: scale });
  let i = 0;
  const lanes = Array.from({ length: Math.min(6, js.length) }, async () => {
    const page = await ctx.newPage();
    while (i < js.length) {
      const j = js[i++];
      try {
        await page.goto(j.url, { waitUntil: 'load' });
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: j.out, omitBackground: !!j.transparent, type: 'png' });
      } catch (e) {
        failed++;
        console.error(`shoot failed for ${j.url}: ${e.message}`);
      }
    }
    await page.close();
  });
  await Promise.all(lanes);
  await ctx.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
