#!/usr/bin/env node
/**
 * Puppeteer canvas capture validation test.
 * Renders a colored rectangle on a canvas and takes a screenshot.
 * Usage: node test_puppeteer.js [output_path]
 */
const puppeteer = require("puppeteer");
const path = require("path");

const outputPath = process.argv[2] || path.join(__dirname, "test_puppeteer.png");

(async () => {
  let browser;
  try {
    browser = await puppeteer.launch({
      headless: true,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--use-gl=swiftshader"],
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 512, height: 512 });

    // Render a Three.js-style test: colored rectangle + gradient
    await page.setContent(`
      <!DOCTYPE html>
      <html>
      <body style="margin:0; background:transparent;">
        <canvas id="c" width="512" height="512"></canvas>
        <script>
          const canvas = document.getElementById('c');
          const ctx = canvas.getContext('2d');
          // Background gradient
          const grad = ctx.createLinearGradient(0, 0, 512, 512);
          grad.addColorStop(0, '#1a1a2e');
          grad.addColorStop(1, '#16213e');
          ctx.fillStyle = grad;
          ctx.fillRect(0, 0, 512, 512);
          // Character placeholder (body shape)
          ctx.fillStyle = '#0f3460';
          ctx.fillRect(180, 100, 150, 300);
          // Head circle
          ctx.beginPath();
          ctx.arc(255, 80, 50, 0, Math.PI * 2);
          ctx.fillStyle = '#e94560';
          ctx.fill();
          // Text label
          ctx.fillStyle = '#ffffff';
          ctx.font = '16px monospace';
          ctx.fillText('Video Pipeline - Canvas Test OK', 100, 470);
        </script>
      </body>
      </html>
    `);

    // Wait for canvas to render
    await new Promise((r) => setTimeout(r, 500));

    await page.screenshot({ path: outputPath, omitBackground: true });

    const fs = require("fs");
    const stats = fs.statSync(outputPath);
    console.log(JSON.stringify({
      status: "ok",
      path: outputPath,
      size_bytes: stats.size,
    }));

    process.exit(0);
  } catch (err) {
    console.log(JSON.stringify({
      status: "error",
      error: err.message,
    }));
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
})();
