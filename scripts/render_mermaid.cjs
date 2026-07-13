const fs = require('fs');
const path = require('path');
const { chromium } = require(
  String.raw`C:\Users\DELL\AppData\Local\OpenAI\Codex\runtimes\cua_node\ecfc0d9aa02807e3\bin\node_modules\playwright`,
);

async function main() {
  const [input, mermaidBundle, outBase, widthArg] = process.argv.slice(2);
  if (!input || !mermaidBundle || !outBase) {
    throw new Error('Usage: render_mermaid.cjs <input.mmd> <mermaid.min.js> <output-base> [css-width]');
  }

  const code = fs.readFileSync(path.resolve(input), 'utf8');
  const cssWidth = Number(widthArg || 2400);
  fs.mkdirSync(path.dirname(path.resolve(outBase)), { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    executablePath: String.raw`C:\Program Files\Google\Chrome\Application\chrome.exe`,
  });
  const context = await browser.newContext({
    viewport: { width: Math.max(cssWidth + 96, 1600), height: 1800 },
    deviceScaleFactor: 2,
    colorScheme: 'light',
  });
  const page = await context.newPage();
  await page.setContent(`<!doctype html>
    <html><head><meta charset="utf-8"><style>
      html, body { margin: 0; background: #fff; }
      #host { display: inline-block; padding: 36px; background: #fff; font-family: Arial, sans-serif; }
      svg { max-width: none !important; }
    </style></head><body><div id="host"></div></body></html>`);
  await page.addScriptTag({ path: path.resolve(mermaidBundle) });

  const svg = await page.evaluate(async ({ code, cssWidth }) => {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      theme: 'base',
      deterministicIds: true,
      deterministicIDSeed: 'vlegalai-erd-v2',
      htmlLabels: false,
      flowchart: { useMaxWidth: false, curve: 'basis' },
      er: { useMaxWidth: false },
      themeVariables: {
        fontFamily: 'Arial, sans-serif',
        fontSize: '17px',
        primaryColor: '#F8FAFC',
        primaryTextColor: '#172033',
        primaryBorderColor: '#64748B',
        lineColor: '#64748B',
        tertiaryColor: '#EEF2FF',
      },
    });
    const { svg } = await mermaid.render('vlegalai_diagram', code);
    const host = document.getElementById('host');
    host.innerHTML = svg;
    const element = host.querySelector('svg');
    element.removeAttribute('width');
    element.removeAttribute('height');
    element.style.width = `${cssWidth}px`;
    element.style.height = 'auto';
    element.setAttribute('role', 'img');
    return new XMLSerializer().serializeToString(element);
  }, { code, cssWidth });

  fs.writeFileSync(path.resolve(outBase + '.svg'), svg, 'utf8');
  await page.evaluate(() => document.fonts.ready);
  await page.locator('#host').screenshot({
    path: path.resolve(outBase + '.png'),
    omitBackground: false,
    animations: 'disabled',
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
