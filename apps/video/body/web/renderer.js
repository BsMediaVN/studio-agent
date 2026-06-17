/**
 * Body Animation Renderer — Three.js + GLB + Timeline-driven.
 *
 * Renders a character model with animation clips driven by a JSON timeline.
 * Designed for frame-by-frame capture via Puppeteer (not realtime).
 *
 * API (called via Puppeteer page.evaluate):
 *   await window.initRenderer(width, height)
 *   await window.loadCharacter(glbUrl)
 *   await window.loadAnimation(glbUrl, clipName)
 *   window.setTimeline(timelineJson)
 *   window.renderFrame(timeMs)
 *   window.getHeadPositions() -> array
 */

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

class BodyRenderer {
  constructor(canvas, width, height) {
    this.width = width;
    this.height = height;

    // Scene
    this.scene = new THREE.Scene();
    // Transparent background for alpha compositing
    this.scene.background = null;

    // Camera — positioned for upper body framing
    this.camera = new THREE.PerspectiveCamera(35, width / height, 0.1, 100);
    this.camera.position.set(0, 1.2, 3);
    this.camera.lookAt(0, 1.0, 0);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      preserveDrawingBuffer: true,
      antialias: true,
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(1);
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    // Lighting
    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambient);

    const directional = new THREE.DirectionalLight(0xffffff, 0.8);
    directional.position.set(2, 3, 2);
    this.scene.add(directional);

    const fill = new THREE.DirectionalLight(0xffffff, 0.3);
    fill.position.set(-2, 1, -1);
    this.scene.add(fill);

    // Animation
    this.mixer = null;
    this.clips = {};
    this.activeAction = null;
    this.model = null;
    this.loader = new GLTFLoader();

    // Timeline
    this.timeline = null;
    this.currentClipName = null;

    // Head tracking
    this.headBone = null;
    this.headPositions = [];
  }

  async loadCharacter(url) {
    return new Promise((resolve, reject) => {
      this.loader.load(
        url,
        (gltf) => {
          this.model = gltf.scene;
          this.scene.add(this.model);

          // Create animation mixer
          this.mixer = new THREE.AnimationMixer(this.model);

          // Store any embedded animations
          if (gltf.animations && gltf.animations.length > 0) {
            gltf.animations.forEach((clip, i) => {
              const name = clip.name || `embedded_${i}`;
              this.clips[name] = clip;
            });
          }

          // Find head bone for position tracking
          this.model.traverse((node) => {
            if (node.isBone) {
              const name = node.name.toLowerCase();
              if (
                name === "head" ||
                name === "mixamorighead" ||
                name.includes("head")
              ) {
                if (!this.headBone) {
                  this.headBone = node;
                }
              }
            }
          });

          console.log(
            `Character loaded: ${url}, bones: ${this.headBone ? "head found" : "no head bone"}, clips: ${Object.keys(this.clips).length}`
          );
          resolve();
        },
        undefined,
        (err) => reject(new Error(`Failed to load character: ${err.message}`))
      );
    });
  }

  async loadAnimation(url, clipName) {
    return new Promise((resolve, reject) => {
      this.loader.load(
        url,
        (gltf) => {
          if (gltf.animations && gltf.animations.length > 0) {
            this.clips[clipName] = gltf.animations[0];
            console.log(`Animation loaded: ${clipName} from ${url}`);
          } else {
            console.warn(`No animations found in ${url}`);
          }
          resolve();
        },
        undefined,
        (err) =>
          reject(new Error(`Failed to load animation ${clipName}: ${err.message}`))
      );
    });
  }

  setTimeline(timeline) {
    this.timeline = timeline;
    this.headPositions = [];
    console.log(
      `Timeline set: ${timeline.duration_ms}ms, ${timeline.animations.length} clips`
    );
  }

  _playClip(clipName, crossfadeMs = 300) {
    if (clipName === this.currentClipName) return;

    const clip = this.clips[clipName];
    if (!clip) {
      console.warn(`Clip not found: ${clipName}`);
      return;
    }

    const newAction = this.mixer.clipAction(clip);
    newAction.reset();

    if (this.activeAction) {
      newAction.crossFadeFrom(this.activeAction, crossfadeMs / 1000, true);
    }

    newAction.play();
    this.activeAction = newAction;
    this.currentClipName = clipName;
  }

  _applyCameraAt(timeMs) {
    if (!this.timeline || !this.timeline.camera || this.timeline.camera.length === 0)
      return;

    const cam = this.timeline.camera;

    // Find surrounding keyframes
    let prev = cam[0];
    let next = cam[cam.length - 1];

    for (let i = 0; i < cam.length - 1; i++) {
      if (cam[i].t_ms <= timeMs && cam[i + 1].t_ms >= timeMs) {
        prev = cam[i];
        next = cam[i + 1];
        break;
      }
    }

    // Interpolate
    const range = next.t_ms - prev.t_ms;
    const t = range > 0 ? (timeMs - prev.t_ms) / range : 0;

    const zoom = prev.zoom + (next.zoom - prev.zoom) * t;
    const panX = (prev.pan_x || 0) + ((next.pan_x || 0) - (prev.pan_x || 0)) * t;
    const panY = (prev.pan_y || 0) + ((next.pan_y || 0) - (prev.pan_y || 0)) * t;

    // Apply zoom as camera Z distance
    this.camera.position.z = 3 / zoom;
    this.camera.position.x = panX / 100;
    this.camera.position.y = 1.2 + panY / 100;
    this.camera.lookAt(panX / 100, 1.0 + panY / 100, 0);
  }

  renderFrame(timeMs) {
    if (!this.mixer) {
      this.renderer.render(this.scene, this.camera);
      window.frameReady = true;
      return;
    }

    // Determine which clip should be playing at this time
    if (this.timeline && this.timeline.animations) {
      for (const anim of this.timeline.animations) {
        if (timeMs >= anim.start_ms && timeMs < anim.end_ms) {
          this._playClip(anim.clip, anim.crossfade_ms || 300);
          break;
        }
      }
    }

    // Advance mixer to exact time
    this.mixer.setTime(timeMs / 1000);

    // Apply camera
    this._applyCameraAt(timeMs);

    // Render
    this.renderer.render(this.scene, this.camera);

    // Track head bone position
    if (this.headBone) {
      const worldPos = new THREE.Vector3();
      this.headBone.getWorldPosition(worldPos);

      // Calculate distance from camera BEFORE projecting (world space)
      const dist = this.camera.position.distanceTo(worldPos);
      const scale = Math.max(0.1, Math.min(3.0, 2.0 / Math.max(dist, 0.1)));

      // Project to screen space
      const ndcPos = worldPos.clone().project(this.camera);
      const screenX = ((ndcPos.x + 1) / 2) * this.width;
      const screenY = ((-ndcPos.y + 1) / 2) * this.height;

      this.headPositions.push({
        frame: this.headPositions.length,
        x: Math.round(screenX),
        y: Math.round(screenY),
        scale: Math.round(scale * 100) / 100,
      });
    }

    window.frameReady = true;
  }

  getHeadPositions() {
    return this.headPositions;
  }

  /**
   * Create a simple test scene (no GLB needed) for validation.
   */
  createTestScene() {
    // Simple body-like shape
    const bodyGeo = new THREE.CapsuleGeometry(0.3, 0.8, 8, 16);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x4488cc });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.9;
    this.scene.add(body);

    // Head sphere
    const headGeo = new THREE.SphereGeometry(0.2, 16, 16);
    const headMat = new THREE.MeshStandardMaterial({ color: 0xffcc88 });
    const head = new THREE.Mesh(headGeo, headMat);
    head.position.y = 1.7;
    this.scene.add(head);

    // Arms
    const armGeo = new THREE.CapsuleGeometry(0.08, 0.5, 4, 8);
    const armMat = new THREE.MeshStandardMaterial({ color: 0x4488cc });

    const leftArm = new THREE.Mesh(armGeo, armMat);
    leftArm.position.set(-0.45, 1.0, 0);
    leftArm.rotation.z = 0.3;
    this.scene.add(leftArm);

    const rightArm = new THREE.Mesh(armGeo, armMat.clone());
    rightArm.position.set(0.45, 1.0, 0);
    rightArm.rotation.z = -0.3;
    this.scene.add(rightArm);

    // Store head as trackable (use the mesh position instead of bone)
    this._testHead = head;

    console.log("Test scene created (no GLB)");
  }
}

// --- Global API for Puppeteer ---

let renderer = null;

window.initRenderer = function (width, height) {
  const canvas = document.getElementById("canvas");
  canvas.width = width;
  canvas.height = height;
  renderer = new BodyRenderer(canvas, width, height);
  window.frameReady = false;
  console.log(`Renderer initialized: ${width}x${height}`);
};

window.loadCharacter = async function (url) {
  await renderer.loadCharacter(url);
};

window.loadAnimation = async function (url, clipName) {
  await renderer.loadAnimation(url, clipName);
};

window.setTimeline = function (timeline) {
  renderer.setTimeline(timeline);
};

window.renderFrame = function (timeMs) {
  window.frameReady = false;
  renderer.renderFrame(timeMs);
};

window.getHeadPositions = function () {
  return renderer.getHeadPositions();
};

window.createTestScene = function () {
  renderer.createTestScene();
};
