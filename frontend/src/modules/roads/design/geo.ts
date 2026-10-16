// Earth radius in metres, for a flat-earth projection good enough at segment scale (tens to a
// few hundred metres) — see docs/plan_live_3d_corridor.md for where it stops being good enough
// and what replaces it (a real UTM projection, server-side).
const EARTH_R_M = 6371000;
const DEG = Math.PI / 180;

/** Project [lon, lat] pairs to local metres relative to their own centroid, flipping Y so north
 * is up on screen. Shared by RoadFlowMap (2D) and RoadScene3D (3D curve). */
export function projectLocal(coords: [number, number][]): { x: number; y: number }[] {
  const lat0 = coords.reduce((s, [, lat]) => s + lat, 0) / coords.length;
  const lon0 = coords.reduce((s, [lon]) => s + lon, 0) / coords.length;
  const cosLat0 = Math.cos(lat0 * DEG);
  return coords.map(([lon, lat]) => ({
    x: (lon - lon0) * DEG * EARTH_R_M * cosLat0,
    y: -(lat - lat0) * DEG * EARTH_R_M,
  }));
}
