import { useEffect, useRef, useState } from "react";
import type { DesignElement } from "./api";

// Schematic, not geo-accurate: draws a representative stretch of road, not this segment's real
// alignment. Mirrors CrossSection.tsx's "to scale, not to place" approach, in 3D.
const LENGTH_M = 40;
const MAX_CARS_PER_LANE = 5;

const COLOR: Record<DesignElement["kind"], number> = {
  footpath: 0xd6ccb8,
  tree_strip: 0x3c7a3a,
  cycle_track: 0x5f93c9,
  bus_bay: 0xd99a4e,
  lane: 0x4b4f54,
  median: 0x5a9a4a,
  carriageway: 0x6b7280,
};

type Props = {
  elements: DesignElement[];
  rowCm: number;
  /** Roughly volume/capacity (0-1+); scales how many car boxes sit on the lanes. Omit for none. */
  trafficDensity?: number | null;
  label: string;
};

/** A schematic 3D block model of one cross-section (current or a design option), for a quick
 * "what would this look like" view. Falls back to a text message where WebGL isn't available
 * (e.g. the jsdom test environment) instead of throwing. */
export default function RoadScene3D({ elements, rowCm, trafficDensity, label }: Props) {
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

      const width = el.clientWidth || 400;
      const height = el.clientHeight || 260;
      const rowM = rowCm / 100;

      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0xeaf2f8);

      const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 500);
      camera.position.set(rowM * 0.9, Math.max(rowM * 0.7, 8), LENGTH_M * 0.55);

      renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(width, height);
      el.replaceChildren(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.target.set(0, 0, 0);
      controls.enableDamping = true;
      controls.maxPolarAngle = Math.PI / 2.1;

      scene.add(new THREE.AmbientLight(0xffffff, 0.85));
      const sun = new THREE.DirectionalLight(0xffffff, 0.55);
      sun.position.set(20, 40, 10);
      scene.add(sun);

      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(rowM + 40, LENGTH_M),
        new THREE.MeshStandardMaterial({ color: 0xdfe6ea }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.position.y = -0.02;
      scene.add(ground);

      // Cross-section elements, left to right across X, extruded along Z (the representative stretch).
      let x = -rowM / 2;
      const laneCentres: number[] = [];
      for (const e of elements) {
        const w = Math.max(e.width_m, 0.02);
        const h = e.kind === "footpath" || e.kind === "median" || e.kind === "tree_strip" ? 0.15 : 0.02;
        const mesh = new THREE.Mesh(
          new THREE.BoxGeometry(w, h, LENGTH_M),
          new THREE.MeshStandardMaterial({ color: COLOR[e.kind] ?? 0x999999 }),
        );
        mesh.position.set(x + w / 2, h / 2, 0);
        scene.add(mesh);

        if (e.kind === "lane") laneCentres.push(x + w / 2);

        if (e.kind === "tree_strip") {
          for (let z = -LENGTH_M / 2 + 2; z < LENGTH_M / 2; z += 4) {
            const trunk = new THREE.Mesh(
              new THREE.CylinderGeometry(0.08, 0.1, 0.8),
              new THREE.MeshStandardMaterial({ color: 0x6b4423 }),
            );
            trunk.position.set(x + w / 2, h + 0.4, z);
            scene.add(trunk);
            const canopy = new THREE.Mesh(
              new THREE.ConeGeometry(0.6, 1.2, 8),
              new THREE.MeshStandardMaterial({ color: 0x2e7d32 }),
            );
            canopy.position.set(x + w / 2, h + 1.1, z);
            scene.add(canopy);
          }
        }
        x += w;
      }

      // Simple building blocks beyond each property line, for visual context only.
      const halfRow = rowM / 2;
      for (const side of [-1, 1]) {
        for (let i = 0; i < 4; i++) {
          const bw = 5, bd = 6, bh = 6 + (i % 3) * 3;
          const mesh = new THREE.Mesh(
            new THREE.BoxGeometry(bw, bh, bd),
            new THREE.MeshStandardMaterial({ color: 0xb9c2cc }),
          );
          mesh.position.set(side * (halfRow + 3 + bw / 2), bh / 2, -LENGTH_M / 2 + 5 + i * (bd + 1));
          scene.add(mesh);
        }
      }

      // Car boxes on lane elements, scaled by trafficDensity: a visual hint of congestion, not a
      // simulation (see TrafficImpact.note in the API response).
      const density = Math.max(0, Math.min(1, trafficDensity ?? 0));
      const carsPerLane = Math.round(density * MAX_CARS_PER_LANE);
      laneCentres.forEach((lx, li) => {
        for (let i = 0; i < carsPerLane; i++) {
          const z = -LENGTH_M / 2 + 3 + (i * (LENGTH_M - 6)) / Math.max(carsPerLane, 1) + (li % 2) * 2;
          const car = new THREE.Mesh(
            new THREE.BoxGeometry(1.7, 1.2, 3.6),
            new THREE.MeshStandardMaterial({ color: 0xc0392b }),
          );
          car.position.set(lx, 0.6, z);
          scene.add(car);
        }
      });

      const animate = () => {
        if (disposed || !renderer) return;
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
  }, [elements, rowCm, trafficDensity]);

  return (
    <div>
      {unsupported ? (
        <div data-testid="road-scene-3d-unsupported"
          className="flex h-48 items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs text-slate-500">
          3D preview needs a browser with WebGL.
        </div>
      ) : (
        <div ref={container} data-testid="road-scene-3d" className="h-56 w-full overflow-hidden rounded border border-slate-200" />
      )}
      <p className="mt-1 text-center text-xs text-slate-500">{label}</p>
    </div>
  );
}
