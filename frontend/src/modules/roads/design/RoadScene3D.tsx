import { useEffect, useRef, useState, type ReactNode } from "react";
import type { DesignElement } from "./api";
import { projectLocal } from "./geo";

// Used only when there is no real geometry (shouldn't normally happen — RoadDashboard always has
// the segment's GeoJSON). Keeps the component usable rather than throwing.
const FALLBACK_LENGTH_M = 40;
const MAX_CARS_PER_LANE = 5;
const TREE_SPACING_M = 4;
const BUILDING_SPACING_M = 10;
const MAX_PEDESTRIANS_PER_FOOTPATH = 3;
const STREETLIGHT_SPACING_M = 45; // real point lights add real per-pixel cost on every lit surface in
                                   // range (the ground plane especially) -- this was the actual cause of
                                   // orbit-drag lag at the previous (denser) spacing, not draw-call count
const STREETLIGHT_SPAN_M = 130; // placed over a smaller window than buildings/trees — they matter most near the camera
// Real-world speeds, not fractions of the curve — t-per-frame below is derived from these divided
// by curveLength, so apparent motion looks the same whether the segment is 40 m or 600 m. Before
// this, speed was a flat fraction of the *whole* curve per frame, so a long segment made cars and
// especially pedestrians look like they were sprinting.
const CAR_CRUISE_MPS = 13; // ~47 km/h, free-flowing urban traffic
const CAR_CONGESTED_MPS = 3.2; // crawl, at trafficDensity 1
const PED_SPEED_MPS = 1.3; // a brisk walk
const ASSUMED_FPS = 60;

const COLOR: Record<DesignElement["kind"], number> = {
  footpath: 0xd6ccb8,
  tree_strip: 0x3c7a3a,
  cycle_track: 0x5f93c9,
  bus_bay: 0xd99a4e,
  lane: 0x4b4f54,
  median: 0x5a9a4a,
  carriageway: 0x6b7280,
};
const HEIGHT_M: Record<DesignElement["kind"], number> = {
  footpath: 0.15, median: 0.15, tree_strip: 0.15,
  lane: 0.02, cycle_track: 0.02, bus_bay: 0.02, carriageway: 0.02,
};

/** Asphalt gray tinted toward congestion-red, capped well short of full saturation — this still
 * needs to read as a road surface, not a solid block of paint. */
function laneColor(trafficDensity: number | null | undefined): number {
  const t = Math.min(0.55, Math.max(0, trafficDensity ?? 0));
  const base = { r: 0x3c, g: 0x3f, b: 0x43 }, crit = { r: 0x8a, g: 0x3b, b: 0x33 };
  const r = Math.round(base.r + (crit.r - base.r) * t);
  const g = Math.round(base.g + (crit.g - base.g) * t);
  const b = Math.round(base.b + (crit.b - base.b) * t);
  return (r << 16) | (g << 8) | b;
}

type Props = {
  elements: DesignElement[];
  rowCm: number;
  geometry: { type: "LineString"; coordinates: [number, number][] } | null;
  /** Roughly volume/capacity (0-1+); scales how many cars drive the lanes and how fast. Omit for none. */
  trafficDensity?: number | null;
  label: string;
  /** Optional overlay rendered inside the same bounding box as the canvas (not the label below
   * it) — e.g. RoadDashboard's HUD readouts. Only shown once the scene is actually ready, so it
   * never sits on top of the loading/error placeholders. */
  hud?: ReactNode;
  /** Skips the "{label}" caption under the canvas — for a fullscreen host that already shows the
   * scenario name elsewhere (e.g. RoadDashboard's own top bar), where the caption would just be
   * redundant text sitting over the scene. */
  hideLabel?: boolean;
};

/** A 3D model of one cross-section swept along the segment's real curved alignment, with cars
 * driving the lanes and the road surface tinted by congestion. Falls back to a short straight
 * stretch when there's no geometry, and to a text message where WebGL isn't available (e.g. the
 * jsdom test environment) instead of throwing. See docs/plan_live_3d_corridor.md for the build
 * notes this implements. */
type Status = "loading" | "ready" | "unsupported" | "error";

export default function RoadScene3D({ elements, rowCm, geometry, trafficDensity, label, hud, hideLabel }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    const el = container.current;
    if (!el) return;

    const probe = document.createElement("canvas");
    const supported = !!(probe.getContext("webgl2") || probe.getContext("webgl"));
    if (!supported) {
      setStatus("unsupported");
      return;
    }
    setStatus("loading");

    let disposed = false;
    let renderer: import("three").WebGLRenderer | null = null;
    let controls: import("three/examples/jsm/controls/OrbitControls.js").OrbitControls | null = null;
    let scene: import("three").Scene | null = null;
    let frame = 0;

    (async () => {
      try {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      if (disposed || !el) return;

      type V3 = InstanceType<typeof THREE.Vector3>;

      const width = el.clientWidth || 400;
      const height = el.clientHeight || 260;
      const rowM = rowCm / 100;

      // A dusk "control room" look to match the dashboard it sits in, rather than a flat daylight
      // scene: dark sky/fog (no washed-out white horizon), a low warm "sunset" key light for rim
      // contrast on the buildings, and a cool blue fill so shadowed faces don't go pure black.
      const SKY_COLOR = 0x0c1526;
      scene = new THREE.Scene();
      scene.background = new THREE.Color(SKY_COLOR);
      scene.fog = new THREE.Fog(SKY_COLOR, 60, 240);

      const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);

      renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(width, height);
      el.replaceChildren(renderer.domElement);

      controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.maxPolarAngle = Math.PI / 2.1;

      scene.add(new THREE.HemisphereLight(0x4a6690, 0x1c1812, 0.75));
      const sun = new THREE.DirectionalLight(0xffb067, 1.3);
      sun.position.set(-26, 18, 14);
      scene.add(sun);
      const fill = new THREE.DirectionalLight(0x6fa8ff, 0.3);
      fill.position.set(22, 14, -18);
      scene.add(fill);

      // The curve: the segment's real alignment, projected to local metres, or a short straight
      // fallback. CatmullRomCurve3's *At methods are arc-length parameterised, so `t` in 0..1
      // below always means "this far along the road", not "this far through the point list".
      const curvePoints: V3[] = geometry && geometry.coordinates.length >= 2
        ? projectLocal(geometry.coordinates).map((p) => new THREE.Vector3(p.x, 0, p.y))
        : [new THREE.Vector3(0, 0, -FALLBACK_LENGTH_M / 2), new THREE.Vector3(0, 0, FALLBACK_LENGTH_M / 2)];
      const curve = new THREE.CatmullRomCurve3(curvePoints, false, "catmullrom", 0.4);
      const curveLength = curve.getLength();
      const segments = Math.max(12, Math.min(72, Math.round(curveLength / 4)));

      // Decorative content (ground extent, buildings, lane-divider dashes) only needs to cover
      // roughly what the camera's default framing shows plus some pan/zoom room — building it for
      // the whole corridor on a long road just wastes meshes nobody will see, and (for the ground)
      // reads as one huge flat-colour patch. Trees stay instanced across the full alignment since
      // that's cheap regardless of count.
      const windowSpan = Math.min(curveLength, 200);
      const windowFrac = Math.min(1, windowSpan / curveLength);
      const tWinStart = Math.max(0, 0.5 - windowFrac / 2);
      const tWinEnd = Math.min(1, 0.5 + windowFrac / 2);

      const up = new THREE.Vector3(0, 1, 0);
      const clampT = (t: number) => Math.min(0.999, Math.max(0, t));
      function frameAt(t: number) {
        const ct = clampT(t);
        const point = curve.getPointAt(ct);
        const tangent = curve.getTangentAt(ct).normalize();
        const right = new THREE.Vector3().crossVectors(tangent, up).normalize();
        return { point, tangent, right };
      }

      const mid = frameAt(0.5).point;

      /** A small tiled texture (two faint seams) instead of one flat fill, so the ground reads
       * as a surface at this scale rather than a solid colour patch. */
      function makeGroundTexture() {
        const size = 128;
        const c = document.createElement("canvas");
        c.width = c.height = size;
        const ctx = c.getContext("2d")!;
        ctx.fillStyle = "#1c2b2a";
        ctx.fillRect(0, 0, size, size);
        ctx.fillStyle = "rgba(255,255,255,0.045)";
        ctx.fillRect(0, 0, size, 2);
        ctx.fillRect(0, 0, 2, size);
        const tex = new THREE.CanvasTexture(c);
        tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
        return tex;
      }

      const groundSize = windowSpan + rowM + 40;
      const groundTex = makeGroundTexture();
      groundTex.repeat.set(groundSize / 6, groundSize / 6);
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(groundSize, groundSize),
        new THREE.MeshLambertMaterial({ map: groundTex }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.set(mid.x, -0.02, mid.z);
      scene.add(ground);

      /** A solid ribbon (top face + two side walls) of constant width [x0, x1] and height h,
       * swept along the curve — the curved equivalent of the old straight BoxGeometry per
       * element. DoubleSide avoids having to track winding direction per face. */
      function ribbon(x0: number, x1: number, h: number) {
        const positions: number[] = [];
        const pts: { tl: V3; tr: V3; bl: V3; br: V3 }[] = [];
        for (let i = 0; i <= segments; i++) {
          const { point, right } = frameAt(i / segments);
          const bl = point.clone().addScaledVector(right, x0);
          const br = point.clone().addScaledVector(right, x1);
          const tl = bl.clone(); tl.y += h;
          const tr = br.clone(); tr.y += h;
          pts.push({ tl, tr, bl, br });
        }
        const quad = (a: V3, b: V3, c: V3, d: V3) => {
          positions.push(a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z);
          positions.push(a.x, a.y, a.z, c.x, c.y, c.z, d.x, d.y, d.z);
        };
        for (let i = 0; i < segments; i++) {
          const p0 = pts[i], p1 = pts[i + 1];
          quad(p0.tl, p0.tr, p1.tr, p1.tl);
          if (h > 0.001) {
            quad(p0.bl, p0.tl, p1.tl, p1.bl);
            quad(p0.br, p0.tr, p1.tr, p1.br);
          }
        }
        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geo.computeVertexNormals();
        return geo;
      }

      // Cross-section elements, left to right across the curve's local X, swept along its length.
      let x = -rowM / 2;
      let prevKind: DesignElement["kind"] | null = null;
      const laneCentres: number[] = [];
      const treeCentres: number[] = [];
      const footpathCentres: number[] = [];
      const laneDividers: number[] = [];
      for (const e of elements) {
        const w = Math.max(e.width_m, 0.02);
        const x0 = x, x1 = x + w;
        const color = e.kind === "lane" ? laneColor(trafficDensity) : (COLOR[e.kind] ?? 0x999999);
        const mesh = new THREE.Mesh(
          ribbon(x0, x1, HEIGHT_M[e.kind] ?? 0.02),
          new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide }),
        );
        scene.add(mesh);
        if (e.kind === "lane") laneCentres.push((x0 + x1) / 2);
        if (e.kind === "tree_strip") treeCentres.push((x0 + x1) / 2);
        if (e.kind === "footpath") footpathCentres.push((x0 + x1) / 2);
        if (prevKind === "lane" && e.kind === "lane") laneDividers.push(x0);
        prevKind = e.kind;
        x = x1;
      }

      // Lane-divider dashes: thin instanced marks between adjacent travel lanes, within the
      // camera's default window — a visual cue, not a lane-marking survey.
      if (laneDividers.length) {
        const dashLen = 3, gapLen = 2.5, cycle = dashLen + gapLen;
        const dashesPerLine = Math.max(1, Math.floor(windowSpan / cycle));
        const dashMesh = new THREE.InstancedMesh(
          new THREE.BoxGeometry(0.2, 0.015, dashLen),
          new THREE.MeshBasicMaterial({ color: 0xfafaf0 }), // self-lit so it reads clearly against the road even at dusk
          laneDividers.length * dashesPerLine,
        );
        const m = new THREE.Matrix4();
        let idx = 0;
        laneDividers.forEach((xc) => {
          for (let i = 0; i < dashesPerLine; i++) {
            const t = tWinStart + windowFrac * ((i + 0.5) * cycle / windowSpan);
            if (t > tWinEnd) continue;
            const { point, right, tangent } = frameAt(t);
            const pos = point.clone().addScaledVector(right, xc);
            pos.y += 0.025;
            m.makeBasis(right, up, tangent);
            m.setPosition(pos.x, pos.y, pos.z);
            dashMesh.setMatrixAt(idx++, m);
          }
        });
        dashMesh.count = idx;
        dashMesh.instanceMatrix.needsUpdate = true;
        scene.add(dashMesh);
      }

      // Trees: instanced (one draw call per part regardless of count) along each tree_strip,
      // spaced roughly every TREE_SPACING_M along the curve's real length. Two stacked canopy
      // cones (not one squat cone) for a fuller, more tree-like silhouette at a height that
      // actually reads next to 6-15 m buildings instead of looking like a shrub.
      if (treeCentres.length) {
        const perStrip = Math.max(1, Math.round(curveLength / TREE_SPACING_M));
        const total = treeCentres.length * perStrip;
        const trunks = new THREE.InstancedMesh(
          new THREE.CylinderGeometry(0.12, 0.17, 1.6), new THREE.MeshLambertMaterial({ color: 0x5a3a22 }), total);
        const canopyLower = new THREE.InstancedMesh(
          new THREE.ConeGeometry(1.0, 1.8, 8), new THREE.MeshLambertMaterial({ color: 0x2d6b32 }), total);
        const canopyUpper = new THREE.InstancedMesh(
          new THREE.ConeGeometry(0.62, 1.3, 8), new THREE.MeshLambertMaterial({ color: 0x3c8a41 }), total);
        const m = new THREE.Matrix4();
        let idx = 0;
        treeCentres.forEach((xc) => {
          for (let i = 0; i < perStrip; i++) {
            const { point, right } = frameAt((i + 0.5) / perStrip);
            const base = point.clone().addScaledVector(right, xc);
            m.makeTranslation(base.x, base.y + 0.8, base.z); trunks.setMatrixAt(idx, m);
            m.makeTranslation(base.x, base.y + 2.3, base.z); canopyLower.setMatrixAt(idx, m);
            m.makeTranslation(base.x, base.y + 3.1, base.z); canopyUpper.setMatrixAt(idx, m);
            idx++;
          }
        });
        trunks.instanceMatrix.needsUpdate = true;
        canopyLower.instanceMatrix.needsUpdate = true;
        canopyUpper.instanceMatrix.needsUpdate = true;
        scene.add(trunks, canopyLower, canopyUpper);
      }

      // Buildings: schematic context blocks beyond the row on each side, following the curve —
      // not real building footprints (see RoadFlowMap for the same simplification). Only placed
      // within the camera's default window (see windowSpan above).
      const halfRow = rowM / 2;
      const buildingCount = Math.max(2, Math.round(windowSpan / BUILDING_SPACING_M));
      for (const side of [-1, 1]) {
        for (let i = 0; i < buildingCount; i++) {
          const t = tWinStart + windowFrac * ((i + 0.5) / buildingCount);
          const { point, right, tangent } = frameAt(t);
          const bw = 5, bd = 6, bh = 6 + (i % 3) * 3;
          const base = point.clone().addScaledVector(right, side * (halfRow + 3 + bw / 2));
          const shade = 0x323c4a + (i % 4) * 0x060504; // subtle per-building variation, not a flat wall of identical boxes
          const mesh = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), new THREE.MeshLambertMaterial({ color: shade }));
          mesh.position.set(base.x, bh / 2, base.z);
          mesh.lookAt(base.x + tangent.x, bh / 2, base.z + tangent.z);
          scene.add(mesh);

          // Lit windows — self-lit (MeshBasicMaterial), so they read as warm light at dusk
          // regardless of the scene's directional lighting, big and frequent enough to actually
          // read at this camera distance rather than disappear into a dark box. DoubleSide so
          // they're visible from outside regardless of which way lookAt rotated the building.
          if ((i + (side > 0 ? 1 : 0)) % 2 === 0) {
            const winMat = new THREE.MeshBasicMaterial({ color: 0xffd98a, side: THREE.DoubleSide });
            const floors = Math.max(1, Math.floor(bh / 2.5));
            for (let fl = 0; fl < floors; fl++) {
              const winY = -bh / 2 + 1.2 + fl * 2.3;
              const front = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.3), winMat);
              front.position.set(0, winY, -bd / 2 - 0.03);
              mesh.add(front);
              const sideFace = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.3), winMat);
              sideFace.rotation.y = Math.PI / 2;
              sideFace.position.set(-bw / 2 - 0.03, winY, 0);
              mesh.add(sideFace);
            }
          }
        }
      }

      // Background city context: a sparser, semi-transparent second layer of blocks further out,
      // plus a couple of flat cross-street hints with a few faint blocks along them — "other
      // roads can be seen in the background", without actually modelling a city grid. Cheap
      // (transparent, unlit basic material, no windows) since it's purely background depth.
      const farBuildingCount = Math.max(1, Math.round(buildingCount / 2));
      const farMat = new THREE.MeshBasicMaterial({ color: 0x2a3142, transparent: true, opacity: 0.4 });
      for (const side of [-1, 1]) {
        for (let i = 0; i < farBuildingCount; i++) {
          const t = tWinStart + windowFrac * ((i + 0.5) / farBuildingCount);
          const { point, right, tangent } = frameAt(t);
          const bw = 7, bd = 8, bh = 8 + (i % 4) * 4;
          const base = point.clone().addScaledVector(right, side * (halfRow + 14 + bw / 2));
          const mesh = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), farMat);
          mesh.position.set(base.x, bh / 2, base.z);
          mesh.lookAt(base.x + tangent.x, bh / 2, base.z + tangent.z);
          scene.add(mesh);
        }
      }

      const crossMat = new THREE.MeshBasicMaterial({ color: 0x3a3f46, transparent: true, opacity: 0.3 });
      [0.22, 0.75].forEach((tc) => {
        const { point, right } = frameAt(Math.min(0.97, Math.max(0.03, tc)));
        const crossLen = 70;
        const strip = new THREE.Mesh(new THREE.BoxGeometry(6, 0.03, crossLen), crossMat);
        strip.position.set(point.x, 0.015, point.z);
        strip.lookAt(point.x + right.x, 0.015, point.z + right.z);
        scene!.add(strip);
        // a couple of faint blocks flanking the cross street, for depth rather than a bare strip
        [-24, 24].forEach((off) => {
          const base = point.clone().addScaledVector(right, off);
          const bh2 = 7;
          const block = new THREE.Mesh(new THREE.BoxGeometry(6, bh2, 6), farMat);
          block.position.set(base.x, bh2 / 2, base.z);
          scene!.add(block);
        });
      });

      // Streetlights: illustrative placement (no real fixture dataset — same simplification as
      // the buildings/trees above), but real THREE.PointLights, which is the point: the dusk
      // scene above is intentionally dim, and these are what should light it back up near the
      // road instead of leaving it looking flatly dark. Spaced wider and over a smaller span than
      // buildings/trees since each one adds real per-pixel lighting cost.
      const lightCount = Math.max(1, Math.round(Math.min(windowSpan, STREETLIGHT_SPAN_M) / STREETLIGHT_SPACING_M));
      const lightSpan = Math.min(windowFrac, STREETLIGHT_SPAN_M / curveLength);
      const poleMat = new THREE.MeshLambertMaterial({ color: 0x24262b });
      const lampGlowMat = new THREE.MeshBasicMaterial({ color: 0xffdf9e });
      for (const side of [-1, 1]) {
        for (let i = 0; i < lightCount; i++) {
          const t = 0.5 - lightSpan / 2 + lightSpan * ((i + 0.5) / lightCount);
          const { point, right } = frameAt(t);
          const base = point.clone().addScaledVector(right, side * (halfRow + 0.6));
          const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.07, 4.2), poleMat);
          pole.position.set(base.x, 2.1, base.z);
          scene.add(pole);
          // A short arm reaching over the footpath toward the road, like a real street lamp.
          const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 1.0), poleMat);
          arm.rotation.z = Math.PI / 2.3 * -side;
          arm.position.set(base.x - side * 0.4, 4.1, base.z);
          scene.add(arm);
          const lampPos = { x: base.x - side * 0.8, y: 4.25, z: base.z };
          const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.3, 10, 10), lampGlowMat);
          lamp.position.set(lampPos.x, lampPos.y, lampPos.z);
          scene.add(lamp);
          // A bigger, translucent halo behind the lamp — a cheap stand-in for real bloom
          // post-processing, so the light source itself is unmistakable, not just its ground pool.
          const halo = new THREE.Mesh(
            new THREE.SphereGeometry(0.75, 10, 10),
            new THREE.MeshBasicMaterial({ color: 0xffdf9e, transparent: true, opacity: 0.22 }),
          );
          halo.position.set(lampPos.x, lampPos.y, lampPos.z);
          scene.add(halo);
          const light = new THREE.PointLight(0xffc97a, 9, 18, 2);
          light.position.set(lampPos.x, lampPos.y, lampPos.z);
          scene.add(light);
        }
      }

      // Driving cars: animated along the curve's arc length each frame, oriented to the tangent —
      // a visual hint of congestion (count and speed from trafficDensity), not a simulation. Each
      // is a chassis + cabin pair (not one flat box) with a few common car colours, so they read
      // as cars rather than coloured bricks.
      const density = Math.max(0, Math.min(1, trafficDensity ?? 0));
      const carsPerLane = Math.round(density * MAX_CARS_PER_LANE);
      const carSpeedMps = CAR_CRUISE_MPS - density * (CAR_CRUISE_MPS - CAR_CONGESTED_MPS);
      const carTPerFrame = carSpeedMps / ASSUMED_FPS / curveLength;
      const chassisGeo = new THREE.BoxGeometry(1.8, 0.55, 4.0);
      const cabinGeo = new THREE.BoxGeometry(1.5, 0.5, 2.0);
      const CAR_COLORS = [0xd1d5db, 0x2b2f36, 0xb91c1c, 0x1d4ed8, 0x4b5563, 0xf3f4f6];
      const cars: { mesh: InstanceType<typeof THREE.Group>; t: number; speed: number; xc: number }[] = [];
      laneCentres.forEach((xc, li) => {
        // Adjacent lanes travel opposite directions, like real two-way traffic, instead of every
        // car on the segment drifting the same way.
        const dir = li % 2 === 0 ? 1 : -1;
        for (let i = 0; i < carsPerLane; i++) {
          const color = CAR_COLORS[(li * 3 + i) % CAR_COLORS.length];
          const mat = new THREE.MeshLambertMaterial({ color });
          const group = new THREE.Group();
          const chassis = new THREE.Mesh(chassisGeo, mat);
          chassis.position.y = 0.3;
          const cabin = new THREE.Mesh(cabinGeo, new THREE.MeshLambertMaterial({ color: 0x1b2430 }));
          cabin.position.set(0, 0.68, -0.3);
          group.add(chassis, cabin);
          scene!.add(group);
          cars.push({
            mesh: group, xc,
            t: (i / Math.max(carsPerLane, 1) + li * 0.37) % 1,
            speed: dir * carTPerFrame,
          });
        }
      });

      // Walking pedestrians: a visual cue on footpaths, not traffic data (there's no pedestrian
      // count in the model) — a modest fixed number per footpath, walking both directions at a
      // slower, constant pace, same per-frame animation technique as the cars.
      const PED_COLORS = [0x3b5bdb, 0xd9480f, 0x2b8a3e, 0x862e9c, 0x1098ad];
      const pedBodyGeo = new THREE.BoxGeometry(0.32, 0.85, 0.2);
      const pedHeadGeo = new THREE.SphereGeometry(0.15, 8, 8);
      const pedTPerFrame = PED_SPEED_MPS / ASSUMED_FPS / curveLength;
      const pedestrians: { mesh: InstanceType<typeof THREE.Group>; t: number; speed: number; xc: number }[] = [];
      footpathCentres.forEach((xc, fi) => {
        for (let i = 0; i < MAX_PEDESTRIANS_PER_FOOTPATH; i++) {
          const color = PED_COLORS[(fi * 7 + i) % PED_COLORS.length];
          const group = new THREE.Group();
          const body = new THREE.Mesh(pedBodyGeo, new THREE.MeshLambertMaterial({ color }));
          body.position.y = 0.52;
          const head = new THREE.Mesh(pedHeadGeo, new THREE.MeshLambertMaterial({ color: 0xe8c39e }));
          head.position.y = 1.05;
          group.add(body, head);
          scene!.add(group);
          pedestrians.push({
            mesh: group, xc,
            t: (i / MAX_PEDESTRIANS_PER_FOOTPATH + fi * 0.5) % 1,
            speed: (i % 2 === 0 ? 1 : -1) * pedTPerFrame * (0.85 + (i / MAX_PEDESTRIANS_PER_FOOTPATH) * 0.3),
          });
        }
      });

      // Frame a representative stretch of the corridor around its midpoint, not the whole
      // thing — a long segment (hundreds of metres) framed in full would put the camera so far
      // up that the road and buildings shrink to an invisible sliver. OrbitControls still lets
      // the viewer pan/zoom to see more of what was built along the rest of the curve.
      const viewSpan = Math.min(curveLength, 120);
      const dist = Math.max(viewSpan, rowM * 2, 16) * 0.75;
      const center = mid;
      camera.position.set(center.x + dist * 0.6, Math.max(dist * 0.55, 14), center.z + dist * 0.6);
      controls.target.copy(center);

      const animate = () => {
        if (disposed || !renderer || !scene || !controls) return;
        cars.forEach((c) => {
          c.t = (c.t + c.speed + 1) % 1;
          const { point, right, tangent } = frameAt(c.t);
          const dir = c.speed >= 0 ? tangent : tangent.clone().multiplyScalar(-1);
          const pos = point.clone().addScaledVector(right, c.xc);
          c.mesh.position.set(pos.x, 0.6, pos.z);
          c.mesh.lookAt(pos.x + dir.x, 0.6, pos.z + dir.z);
        });
        pedestrians.forEach((p) => {
          p.t = (p.t + p.speed + 1) % 1;
          const { point, right, tangent } = frameAt(p.t);
          const dir = p.speed >= 0 ? tangent : tangent.clone().multiplyScalar(-1);
          const pos = point.clone().addScaledVector(right, p.xc);
          p.mesh.position.set(pos.x, 0, pos.z);
          p.mesh.lookAt(pos.x + dir.x, 0, pos.z + dir.z);
        });
        controls.update();
        renderer.render(scene, camera);
        frame = requestAnimationFrame(animate);
      };
      if (!disposed) setStatus("ready");
      animate();
      } catch (err) {
        console.error("RoadScene3D failed to build the 3D view:", err);
        if (!disposed) setStatus("error");
      }
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      // three.js doesn't track GPU resources with JS GC — every geometry/material/texture
      // allocated above must be disposed by hand, or re-mounting this component (e.g. toggling
      // Today/option on the dashboard) leaks VRAM until the tab crashes.
      scene?.traverse((obj) => {
        const mesh = obj as import("three").Mesh | import("three").InstancedMesh;
        mesh.geometry?.dispose?.();
        const mat = mesh.material;
        const mats = Array.isArray(mat) ? mat : mat ? [mat] : [];
        mats.forEach((m) => {
          (m as import("three").MeshLambertMaterial).map?.dispose?.();
          m.dispose();
        });
      });
      controls?.dispose();
      renderer?.dispose();
      el.replaceChildren();
    };
  }, [elements, rowCm, trafficDensity, geometry]);

  return (
    <div className="flex h-full w-full flex-col">
      <div className="relative min-h-0 flex-1">
        {status !== "unsupported" && status !== "error" && (
          <div ref={container} data-testid="road-scene-3d" className="h-full w-full overflow-hidden rounded border border-slate-200" />
        )}
        {status === "loading" && (
          <div data-testid="road-scene-3d-loading"
            className="absolute inset-0 flex items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs text-slate-400">
            Loading 3D view…
          </div>
        )}
        {status === "unsupported" && (
          <div data-testid="road-scene-3d-unsupported"
            className="flex h-full items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs text-slate-500">
            3D preview needs a browser with WebGL.
          </div>
        )}
        {status === "error" && (
          <div data-testid="road-scene-3d-error"
            className="flex h-full items-center justify-center rounded border border-slate-200 bg-slate-50 px-4 text-center text-xs text-slate-500">
            Couldn't build the 3D view for this road. Try "Today" / "This option" again, or reload the page.
          </div>
        )}
        {status === "ready" && hud}
      </div>
      {!hideLabel && <p className="mt-1 shrink-0 text-center text-xs text-slate-500">{label}</p>}
    </div>
  );
}
