// Print an HTML file to A4 PDF with headless Chromium (Playwright).
// Usage: node scripts/html_to_pdf.js in.html out.pdf
const { chromium } = require('playwright');
const path = require('path');
(async () => {
  const [inp, out] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(inp), { waitUntil: 'networkidle' });
  await page.pdf({ path: out, format: 'A4', printBackground: true,
    margin: { top: '12mm', bottom: '12mm', left: '14mm', right: '14mm' } });
  await browser.close();
})();
