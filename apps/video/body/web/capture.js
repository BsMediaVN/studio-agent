#!/usr/bin/env node
/**
 * Puppeteer frame-by-frame capture for body animation.
 *
 * Usage:
 *   node capture.js --config <config.json> --output <output_dir>
 *
 * Config JSON:
 *   {
 *     "width": 1280,
 *     "height": 720,
 *     "fps": 30,
 *     "duration_ms": 30000,
 *     "character_url": "file:///path/to/model.glb",
 *     "animation_clips": {"idle": "file:///path/to/idle.glb", ...},
 *     "timeline": { ... },
 *     "test_mode": false
 *   }
 */

const puppeteer = require("puppeteer");
const http = require("http");
const os = require("os");
const fs = require("fs");
const path = require("path");

async function main() {
  // Parse args
  const args = parseArgs(process.argv.slice(2));
  const config = JSON.parse(fs.readFileSync(args.config, "utf-8"));
  const outputDir = args.output;

  const framesDir = path.join(outputDir, "frames");
  fs.mkdirSync(framesDir, { recursive: true });

  const width = config.width || 1280;
  const height = config.height || 720;
  const fps = config.fps || 30;
  const durationMs = config.duration_ms || 10000;
  const totalFrames = Math.ceil((durationMs / 1000) * fps);
  const frameDeltaMs = 1000 / fps;

  console.log(
    JSON.stringify({
      status: "starting",
      width,
      height,
      fps,
      duration_ms: durationMs,
      total_frames: totalFrames,
    })
  );

  // Launch browser
  const browser = await puppeteer.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--enable-webgl",
      "--ignore-gpu-blocklist",
      `--window-size=${width},${height}`,
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width, height });

  // Serve web dir via HTTP (file:// + ES modules = CORS block)
  const webDir = __dirname;
  const server = await startFileServer(webDir);
  const serverPort = server.address().port;

  // Wrap everything in try/finally to ensure cleanup on any error
  try {

  // Load renderer page via HTTP
  await page.goto(`http://localhost:${serverPort}/index.html`, {
    waitUntil: "networkidle0",
  });

  // Wait for Three.js to load
  await page.waitForFunction("typeof window.initRenderer === 'function'", {
    timeout: 15000,
  });

  // Initialize renderer
  await page.evaluate(
    (w, h) => window.initRenderer(w, h),
    width,
    height
  );

  // Rewrite /asset/ URLs to use local HTTP server
  const baseUrl = `http://localhost:${serverPort}`;
  function rewriteUrl(url) {
    if (url && url.startsWith("/asset/")) return baseUrl + url;
    if (url && url.startsWith("http")) return url;
    return baseUrl + "/" + url;
  }

  // Load character or test scene
  if (config.test_mode) {
    await page.evaluate(() => window.createTestScene());
    console.log(JSON.stringify({ status: "test_scene_created" }));
  } else {
    if (config.character_url) {
      const charUrl = rewriteUrl(config.character_url);
      await page.evaluate(
        (url) => window.loadCharacter(url),
        charUrl
      );
      console.log(JSON.stringify({ status: "character_loaded" }));
    }

    // Load animation clips
    if (config.animation_clips) {
      for (const [name, url] of Object.entries(config.animation_clips)) {
        try {
          const clipUrl = rewriteUrl(url);
          await page.evaluate(
            (u, n) => window.loadAnimation(u, n),
            clipUrl,
            name
          );
          console.log(
            JSON.stringify({ status: "animation_loaded", clip: name })
          );
        } catch (err) {
          console.error(
            JSON.stringify({
              status: "animation_load_error",
              clip: name,
              error: err.message,
            })
          );
        }
      }
    }
  }

  // Set timeline
  if (config.timeline) {
    await page.evaluate(
      (tl) => window.setTimeline(tl),
      config.timeline
    );
  }

  // Capture frames
  console.log(
    JSON.stringify({ status: "capturing", total_frames: totalFrames })
  );

  for (let i = 0; i < totalFrames; i++) {
    const timeMs = i * frameDeltaMs;

    // Render frame
    await page.evaluate((t) => window.renderFrame(t), timeMs);

    // Wait for frame ready
    await page.waitForFunction("window.frameReady === true", {
      timeout: 5000,
    });

    // Capture screenshot
    const framePath = path.join(framesDir, `${String(i).padStart(6, "0")}.png`);
    await page.screenshot({
      path: framePath,
      omitBackground: true,
    });

    // Progress every 30 frames
    if (i % fps === 0) {
      const pct = Math.round((i / totalFrames) * 100);
      console.log(
        JSON.stringify({
          status: "progress",
          frame: i,
          total: totalFrames,
          percent: pct,
        })
      );
    }
  }

  // Export head positions
  const headPositions = await page.evaluate(() => window.getHeadPositions());
  const headPosPath = path.join(outputDir, "head_positions.json");
  fs.writeFileSync(headPosPath, JSON.stringify(headPositions, null, 2));

  console.log(
    JSON.stringify({
      status: "complete",
      frames_captured: totalFrames,
      frames_dir: framesDir,
      head_positions: headPosPath,
    })
  );

  } finally {
    // Cleanup: always close browser and server
    await browser.close().catch(() => {});
    server.close();
  }
}

/**
 * Start a simple static file server for the web directory.
 * Returns a promise that resolves to the HTTP server.
 */
function startFileServer(rootDir) {
  const mimeTypes = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".json": "application/json",
    ".css": "text/css",
    ".png": "image/png",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
  };

  // Allowed directories for serving files
  const assetsDir = path.resolve(path.join(rootDir, "..", "assets"));
  const allowedDirs = [
    path.resolve(rootDir) + path.sep,
    path.resolve(os.tmpdir()) + path.sep,
    assetsDir + path.sep,
  ];

  function isPathAllowed(absPath) {
    const resolved = path.resolve(absPath);
    return allowedDirs.some((dir) => resolved.startsWith(dir));
  }

  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let filePath;

      // Route: /asset/<absolute-path> for GLB files from temp dirs
      if (req.url.startsWith("/asset/")) {
        filePath = decodeURIComponent(req.url.slice(7));
      } else {
        filePath = path.join(rootDir, decodeURIComponent(req.url));
      }

      filePath = path.resolve(filePath);

      // Security: validate path is within allowed directories
      if (!isPathAllowed(filePath)) {
        res.writeHead(403);
        res.end("Forbidden");
        return;
      }

      fs.readFile(filePath, (err, data) => {
        if (err) {
          res.writeHead(404);
          res.end();
          return;
        }
        const ext = path.extname(filePath).toLowerCase();
        const mime = mimeTypes[ext] || "application/octet-stream";
        res.writeHead(200, { "Content-Type": mime });
        res.end(data);
      });
    });

    srv.listen(0, "127.0.0.1", () => {
      console.log(
        JSON.stringify({
          status: "server_started",
          port: srv.address().port,
        })
      );
      resolve(srv);
    });
  });
}

function parseArgs(argv) {
  const args = { config: null, output: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--config" && argv[i + 1]) args.config = argv[++i];
    if (argv[i] === "--output" && argv[i + 1]) args.output = argv[++i];
  }
  if (!args.config || !args.output) {
    console.error("Usage: node capture.js --config <config.json> --output <dir>");
    process.exit(1);
  }
  return args;
}

main().catch((err) => {
  console.error(JSON.stringify({ status: "error", error: err.message }));
  process.exit(1);
});
