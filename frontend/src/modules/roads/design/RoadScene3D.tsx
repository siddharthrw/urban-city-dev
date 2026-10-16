import { useEffect, useRef, useState } from "react";
import type { DesignElement } from "./api";
import { projectLocal } from "./geo";

// Used only when there is no real geometry (shouldn't normally happen — RoadDashboard always has
// the segment's GeoJSON). Keeps the component usable rather than throwing.
const FALLBACK_LENGTH_M = 40;
const MAX_CARS_PER_LANE = 5;
const TREE_SPACING_M = 4;
const BUILDING_SPACING_M = 10;

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

function laneColor(trafficDensity: number | null | undefined): number {
  const t = Math.max(0, Math.min(1, trafficDensity ?? 0));
  const base = { r: 0x4b, g: 0x4f, b: 0x54 }, crit = { r: 0xc0, g: 0x39, b: 0x2b };
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
};

/** A 3D model of one cross-section swept along the segment's real curved alignment, with cars
 * driving the lanes and the road surface tinted by congestion. Falls back to a short straight
 * stretch when there's no geometry, and to a text message where WebGL isn't available (e.g. the
 * jsdom test environment) instead of throwing. See docs/plan_live_3d_corridor.md for the build
 * notes this implements. */
export default function RoadScene3D({ elements, rowCm, geometry, trafficDensity, label }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [unsupported, setUnsupported] = useState(false);

  useEffect(() => {
    const el = container.current;
    if (!el) return;

    const probe = document.createElement("canvas");
    const supported = !!(probe.getContext("webgl2") || probe.getContext("webgl"));
    if (!supported) {
      setUnsupported(true);
      return;
    }
    setUnsupported(false);

    let disposed = false;
    let renderer: import("three").WebGLRenderer | null = null;
    let frame = 0;

    (async () => {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      if (disposed || !el) return;

      type V3 = InstanceType<typeof THREE.Vector3>;

      const width = el.clientWidth || 400;
      const height = el.clientHeight || 260;
      const rowM = rowCm / 100;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xeaf2f8);
      scene.fog = new THREE.Fog(0xeaf2f8, 50, 260);

      const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000);

      renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(width, height);
      el.replaceChildren(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.maxPolarAngle = Math.PI / 2.1;

      scene.add(new THREE.AmbientLight(0xffffff, 0.85));
      const sun = new THREE.DirectionalLight(0xffffff, 0.55);
      sun.position.set(20, 40, 10);
      scene.add(sun);

      // The curve: the segment's real alignment, projected to local metres, or a short straight
      // fallback. CatmullRomCurve3's *At methods are arc-length parameterised, so `t` in 0..1
      // below always means "this far along the road", not "this far through the point list".
      const curvePoints: V3[] = geometry && geometry.coordinates.length >= 2
        ? projectLocal(geometry.coordinates).map((p) => new THREE.Vector3(p.x, 0, p.y))
        : [new THREE.Vector3(0, 0, -FALLBACK_LENGTH_M / 2), new THREE.Vector3(0, 0, FALLBACK_LENGTH_M / 2)];
      const curve = new THREE.CatmullRomCurve3(curvePoints, false, "catmullrom", 0.4);
      const curveLength = curve.getLength();
      const segments = Math.max(12, Math.min(72, Math.round(curveLength / 4)));

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
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(curveLength + rowM + 60, curveLength + rowM + 60),
        new THREE.MeshStandardMaterial({ color: 0xdfe6ea }),
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
      const laneCentres: number[] = [];
      const treeCentres: number[] = [];
      for (const e of elements) {
        const w = Math.max(e.width_m, 0.02);
        const x0 = x, x1 = x + w;
        const color = e.kind === "lane" ? laneColor(trafficDensity) : (COLOR[e.kind] ?? 0x999999);
        const mesh = new THREE.Mesh(
          ribbon(x0, x1, HEIGHT_M[e.kind] ?? 0.02),
          new THREE.MeshStandardMaterial({ color, side: THREE.DoubleSide }),
        );
        scene.add(mesh);
        if (e.kind === "lane") laneCentres.push((x0 + x1) / 2);
        if (e.kind === "tree_strip") treeCentres.push((x0 + x1) / 2);
        x = x1;
      }

      // Trees: instanced (one draw call per part regardless of count) along each tree_strip,
      // spaced roughly every TREE_SPACING_M along the curve's real length.
      if (treeCentres.length) {
        const perStrip = Math.max(1, Math.round(curveLength / TREE_SPACING_M));
        const total = treeCentres.length * perStrip;
        const trunks = new THREE.InstancedMesh(
          new THREE.CylinderGeometry(0.08, 0.1, 0.8), new THREE.MeshStandardMaterial({ color: 0x6b4423 }), total);
        const canopies = new THREE.InstancedMesh(
          new THREE.ConeGeometry(0.6, 1.2, 8), new THREE.MeshStandardMaterial({ color: 0x2e7d32 }), total);
        const m = new THREE.Matrix4();
        let idx = 0;
        treeCentres.forEach((xc) => {
          for (let i = 0; i < perStrip; i++) {
            const { point, right } = frameAt((i + 0.5) / perStrip);
            const base = point.clone().addScaledVector(right, xc);
            m.makeTranslation(base.x, base.y + 0.4, base.z); trunks.setMatrixAt(idx, m);
            m.makeTranslation(base.x, base.y + 1.1, base.z); canopies.setMatrixAt(idx, m);
            idx++;
          }
        });
        trunks.instanceMatrix.needsUpdate = true;
        canopies.instanceMatrix.needsUpdate = true;
        scene.add(trunks, canopies);
      }

      // Buildings: schematic context blocks beyond the row on each side, following the curve —
      // not real building footprints (see RoadFlowMap for the same simplification).
      const halfRow = rowM / 2;
      const buildingCount = Math.max(2, Math.round(curveLength / BUILDING_SPACING_M));
      for (const side of [-1, 1]) {
        for (let i = 0; i < buildingCount; i++) {
          const { point, right, tangent } = frameAt((i + 0.5) / buildingCount);
          const bw = 5, bd = 6, bh = 6 + (i % 3) * 3;
          const base = point.clone().addScaledVector(right, side * (halfRow + 3 + bw / 2));
          const mesh = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), new THREE.MeshStandardMaterial({ color: 0xb9c2cc }));
          mesh.position.set(base.x, bh / 2, base.z);
          mesh.lookAt(base.x + tangent.x, bh / 2, base.z + tangent.z);
          scene.add(mesh);
        }
      }

      // Driving cars: animated along the curve's arc length each frame, oriented to the tangent —
      // a visual hint of congestion (count and speed from trafficDensity), not a simulation.
      const density = Math.max(0, Math.min(1, trafficDensity ?? 0));
      const carsPerLane = Math.round(density * MAX_CARS_PER_LANE);
      const carGeo = new THREE.BoxGeometry(1.7, 1.2, 3.6);
      const cars: { mesh: InstanceType<typeof THREE.Mesh>; t: number; speed: number; xc: number }[] = [];
      laneCentres.forEach((xc, li) => {
        for (let i = 0; i < carsPerLane; i++) {
          const mesh = new THREE.Mesh(carGeo, new THREE.MeshStandardMaterial({ color: 0xc0392b }));
          scene.add(mesh);
          cars.push({
            mesh, xc,
            t: (i / Math.max(carsPerLane, 1) + li * 0.37) % 1,
            speed: 0.0026 - density * 0.0018,
          });
        }
      });

      const box = new THREE.Box3().setFromPoints(curvePoints);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const dist = Math.max(size.x, size.z, 16) * 0.75;
      camera.position.set(center.x + dist * 0.6, Math.max(dist * 0.55, 14), center.z + dist * 0.6);
      controls.target.copy(center);

      const animate = () => {
        if (disposed || !renderer) return;
        cars.forEach((c) => {
          c.t = (c.t + c.speed) % 1;
          const { point, right, tangent } = frameAt(c.t);
          const pos = point.clone().addScaledVector(right, c.xc);
          c.mesh.position.set(pos.x, 0.6, pos.z);
          c.mesh.lookAt(pos.x + tangent.x, 0.6, pos.z + tangent.z);
        });
        controls.update();
        renderer.render(scene, camera);
        frame = requestAnimationFrame(animate);
      };
      animate();
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      renderer?.dispose();
      el.replaceChildren();
    };
  }, [elements, rowCm, trafficDensity, geometry]);

  return (
    <div>
      {unsupported ? (
        <div data-testid="road-scene-3d-unsupported"
          className="flex h-64 items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs text-slate-500">
          3D preview needs a browser with WebGL.
        </div>
      ) : (
        <div ref={container} data-testid="road-scene-3d" className="h-64 w-full overflow-hidden rounded border border-slate-200" />
      )}
      <p className="mt-1 text-center text-xs text-slate-500">{label}</p>
    </div>
  );
}
