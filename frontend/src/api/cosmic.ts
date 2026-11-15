// All calls to the COSMIC TRAIL FastAPI backend (app/main.py).
// The backend routes live under /api; routing is POST /api/route with a JSON body.

export const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export interface Grid {
  x_min: number; x_max: number; y_min: number; y_max: number
  cell: number; width: number; height: number
}

export interface Crs { type: string; lat0: number; lon0: number; radius: number }

export interface Dataset {
  id: string
  kind: string
  dataset_id: string
  terrain_available: boolean
  is_synthetic: boolean
  synthetic_warning: string | null
  coverage_fraction: number
  grid: Grid | null
  crs: Crs | null
}

export interface RouteResult {
  mode: 'shortest' | 'terrain'
  cells: number
  surface_length_3d_m: number
  planimetric_length_m: number
  elevation_gain_m: number
  elevation_loss_m: number
  slope_max_deg: number
  slope_mean_deg: number
  cells_above_caution: number
  warnings: { type: string; text: string }[]
  xy: [number, number][]
  lonlat: [number, number][]
  elevation_profile: number[]
  slope_profile: number[]
  /** Location context from app/context.py: science sites, dune crossings, data quality. */
  context?: RouteContext
}

export interface RouteContext {
  science: { text: string; distance_m?: number; site?: string } | null
  thermal: { text: string; checked: boolean; crossings?: boolean; dunes?: string[]; fraction?: number }
  data: { text: string; hirise_pct: number }
}

/** A suggested map action attached to an ARIA reply (e.g. "Set as Destination B"). */
export interface AssistantAction { type: 'set_destination'; lon: number; lat: number; label: string }

export interface RouteResponse {
  dataset_id: string
  mode_requested: string
  routes: Partial<Record<'shortest' | 'terrain', RouteResult>>
  params_used: {
    max_slope_deg: number
    caution_slope_deg: number
    params_note: string
  }
  tradeoff_summary?: string
  /** compare_routes(): 'identical' | 'equivalent' | 'different'. */
  comparison?: { relation: 'identical' | 'equivalent' | 'different'; text: string; max_separation_m?: number }
  note?: string
  synthetic_warning?: string
}

export interface ScienceCard {
  card_id: string
  site: string
  lon: number
  lat: number
  summary: string
  coord_confidence: string
}

export interface LonLat { lon: number; lat: number }

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    // FastAPI puts errors in `detail`; route errors are {error, message, details}.
    const d = body?.detail
    const msg = typeof d === 'string' ? d : d?.message ?? d?.error ?? JSON.stringify(d ?? body)
    throw new Error(`${res.status}: ${msg}`)
  }
  return body as T
}

export const getHealth = () =>
  fetch(`${BASE}/api/health`).then(r => json<{ status: string; datasets_loaded: string[] }>(r))

export const getDatasets = () =>
  fetch(`${BASE}/api/datasets`).then(r => json<{ datasets: Dataset[] }>(r)).then(d => d.datasets)

export const getMetadata = (datasetId: string) =>
  fetch(`${BASE}/api/datasets/${datasetId}/metadata`).then(r => json<TerrainMetadata>(r))

export const getScienceCards = () =>
  fetch(`${BASE}/api/science/cards`).then(r => json<{ cards: ScienceCard[] }>(r)).then(d => d.cards)

export const layerUrl = (datasetId: string, layer: string) =>
  `${BASE}/api/datasets/${datasetId}/layers/${layer}`

// ---------------------------------------------------------------------------
// Terrain tile scheduling
// Browsers allow ~6 connections per host, so terrain tiles are limited to 4 in flight
// (the app's own API calls always get a connection). While a route is being computed,
// no new tiles are started: tile generation and the pure-Python A* share the backend's
// GIL, and measured routing went from ~9 s to ~33 s when they ran together.
// ---------------------------------------------------------------------------
const MAX_TERRAIN_FETCHES = 4
let terrainInFlight = 0
let terrainPaused = 0
const terrainQueue: (() => void)[] = []

function pumpTerrainQueue() {
  while (terrainPaused === 0 && terrainInFlight < MAX_TERRAIN_FETCHES && terrainQueue.length) {
    terrainInFlight++
    terrainQueue.shift()!()
  }
}

export function fetchTerrainTile(datasetId: string, z: number, x: number, y: number): Promise<ArrayBuffer> {
  return new Promise<void>(resolve => { terrainQueue.push(resolve); pumpTerrainQueue() })
    .then(() => fetch(terrainTileUrl(datasetId, z, x, y)))
    .then(r => { if (!r.ok) throw new Error(`terrain ${r.status}`); return r.arrayBuffer() })
    .finally(() => { terrainInFlight--; pumpTerrainQueue() })
}

/** Run `work` with new terrain tile fetches held back until it settles. */
async function withTerrainPaused<T>(work: () => Promise<T>): Promise<T> {
  terrainPaused++
  try { return await work() } finally { terrainPaused--; pumpTerrainQueue() }
}

export const getRoute = (datasetId: string, start: LonLat, end: LonLat) =>
  withTerrainPaused(() => fetch(`${BASE}/api/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, start, destination: end, mode: 'both' }),
  }).then(r => json<RouteResponse>(r)))

export type LookupStatus = 'ok' | 'nodata' | 'slope_unknown' | 'outside_study_area' | 'terrain_unavailable'

export interface Lookup {
  status: LookupStatus
  in_study_area: boolean
  lon: number
  lat: number
  row?: number
  col?: number
  elevation_m?: number | null
  slope_deg?: number | null
  elevation_source?: string
  /** Outside the analysis grid: coarse MOLA height of the 3D globe (not routing data). */
  context_elevation_m?: number
  context_source?: string
}

/** The backend's own per-cell routing coverage check for a lon/lat. */
export type RouteExportFormat = 'geojson' | 'briefing'

/**
 * Download the route on screen: GeoJSON (LineStrings of [lon, lat, elevation_m], selected
 * route first, plus A/B points) or a plain-text briefing (stats, slope, climb, warnings,
 * context, data sources). Built by the backend (POST /api/route/export/{fmt}, app/db.py).
 * A/B are the route's own first and last points, so the file always matches the route
 * even if the A/B inputs were edited after routing.
 */
export async function downloadRouteExport(fmt: RouteExportFormat, response: RouteResponse, activeMode: 'terrain' | 'shortest') {
  const route = response.routes[activeMode] ?? response.routes.terrain ?? response.routes.shortest
  if (!route?.lonlat.length) throw new Error('No route to export')
  const [first, last] = [route.lonlat[0], route.lonlat[route.lonlat.length - 1]]
  const body = {
    dataset_id: response.dataset_id,
    start: { lon: first[0], lat: first[1] },
    destination: { lon: last[0], lat: last[1] },
    routes: response.routes,
    active_mode: activeMode,
    params_used: response.params_used,
    tradeoff_summary: response.tradeoff_summary,
  }
  const res = await fetch(`${BASE}/api/route/export/${fmt}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    // cell_path (grid indices) is internal and large; the export does not use it.
    body: JSON.stringify(body, (k, v) => (k === 'cell_path' ? undefined : v)),
  })
  if (!res.ok) await json(res)   // throws with the backend's message
  const blob = await res.blob()
  const fallback = fmt === 'geojson' ? 'cosmic_trail_route.geojson' : 'cosmic_trail_briefing.txt'
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const getLookup = (datasetId: string, p: LonLat) =>
  fetch(`${BASE}/api/datasets/${datasetId}/lookup?lon=${p.lon}&lat=${p.lat}`).then(r => json<Lookup>(r))

/** Terrain file metadata (data/<dataset>/metadata.json) — only the parts the globe needs. */
export interface TerrainMetadata {
  analysis?: { x_min: number; y_max: number; cell_size_m: number; width: number; height: number; available?: boolean }
  crs?: Crs
}

export interface Georef {
  west: number; east: number; south: number; north: number
  /** PROJ-style description of the terrain file's CRS, for display. */
  crsLabel: string
  cellM: number
  width: number
  height: number
}

/**
 * Georeference the backend PNG layers from the terrain file's own CRS and bounds.
 *
 * The PNGs are rendered from the analysis grid in analysis.npz, whose metadata gives
 * the CRS (local equidistant cylindrical: lat_ts = lat_0 = lat0, lon_0 = lon0, sphere R)
 * and the grid origin (x_min, y_max = top-left pixel EDGE, rasterio from_origin),
 * cell size and dimensions. Equidistant cylindrical is linear in lon/lat, so the
 * pixel-edge box maps exactly to a lon/lat rectangle:
 *     lon = lon0 + x / (R·cos lat0)   lat = lat0 + y / R      (radians → degrees)
 * Verified against the source DTMs' own CRS (HiRISE DTEEC_023957 / 009505, USGS Gale
 * DEM): best-fit shift 0 m at Bradbury Landing and at a 400 m crater (137.5447°E, 4.4647°S).
 */
export function georefFromMetadata(meta: TerrainMetadata): Georef | null {
  const a = meta.analysis, crs = meta.crs
  if (!a || !crs || a.available === false || crs.type !== 'local_eqc') return null
  const deg = 180 / Math.PI
  const k = crs.radius * Math.cos(crs.lat0 / deg)
  const x_max = a.x_min + a.width * a.cell_size_m
  const y_min = a.y_max - a.height * a.cell_size_m
  return {
    west: crs.lon0 + (a.x_min / k) * deg,
    east: crs.lon0 + (x_max / k) * deg,
    north: crs.lat0 + (a.y_max / crs.radius) * deg,
    south: crs.lat0 + (y_min / crs.radius) * deg,
    crsLabel: `eqc lat_ts=lat_0=${crs.lat0}° lon_0=${crs.lon0}° R=${crs.radius} m`,
    cellM: a.cell_size_m,
    width: a.width,
    height: a.height,
  }
}

export const inGeoref = (g: Georef, p: LonLat) =>
  p.lon >= g.west && p.lon <= g.east && p.lat >= g.south && p.lat <= g.north

/** 3D height tiles served by the backend (app/terrain_tiles.py). */
export interface TerrainInfo {
  available: boolean
  tile_size: number
  reference_height_m: number | null
  sources: string[]
  note: string | null
}

export const getTerrainInfo = (datasetId: string) =>
  fetch(`${BASE}/api/datasets/${datasetId}/terrain`).then(r => json<TerrainInfo>(r))

export const terrainTileUrl = (datasetId: string, z: number, x: number, y: number) =>
  `${BASE}/api/datasets/${datasetId}/terrain/${z}/${x}/${y}`

/** HiRISE photo layer: ortho mosaic clipped to the study area (scripts/build_ortho_mosaic.py),
 *  served as imagery tiles (app/ortho_tiles.py). Bounds in degrees. */
export interface OrthoInfo {
  available: boolean
  /** The mosaic file, e.g. ortho_mosaic.tif. */
  file?: string
  /** HiRISE ortho JP2s merged into it, in priority order. */
  sources?: string[]
  /** Mosaic build tag; part of the tile URLs so rebuilt mosaics bypass the browser cache. */
  version?: string
  west?: number; south?: number; east?: number; north?: number
  resolution_m?: number
  max_level?: number
  credit?: string
  note?: string | null
}

export const getOrthoInfo = (datasetId: string) =>
  fetch(`${BASE}/api/datasets/${datasetId}/ortho`).then(r => json<OrthoInfo>(r))

/** Cesium UrlTemplateImageryProvider template ({z}/{x}/{y}, geographic tiling). */
export const orthoTileTemplate = (datasetId: string, version = '') =>
  `${BASE}/api/datasets/${datasetId}/ortho/{z}/{x}/{y}.png${version ? `?v=${version}` : ''}`

/** Aqueous-mineral detection points (GET /api/layers/minerals). */
export interface MineralLegendItem { class: string; label: string; color: string; count: number }
export interface MineralPoint { c: string; lon: number; lat: number; h?: number }
export interface MineralsLayer {
  available: boolean
  note?: string
  title?: string
  citation?: string
  attribution?: string
  instruments?: string[]
  nature?: string
  legend?: MineralLegendItem[]
  points?: MineralPoint[]
}

export const getMinerals = () => fetch(`${BASE}/api/layers/minerals`).then(r => json<MineralsLayer>(r))

/** ARIA — rule-based assistant (POST /api/assistant/chat). */
export interface AssistantReply {
  reply: string
  data_source: string
  confidence: 'high' | 'medium' | 'low' | 'none'
  intent: string
  location: LonLat
  data: Record<string, unknown>
  caveat: string | null
  follow_up?: string | null
  suggestions?: string[]
  engine: string
}

/** Steep (caution) stretches along a route: how many, and which third of the route has most of them. */
export function cautionStretches(r: RouteResult, caution = 10) {
  let segments = 0, inRun = false
  const thirds = [0, 0, 0]
  r.slope_profile.forEach((s, i) => {
    const over = s > caution
    if (over && !inRun) segments++
    inRun = over
    if (over) thirds[Math.min(2, Math.floor((3 * i) / Math.max(1, r.slope_profile.length)))]++
  })
  const where = segments ? (['start', 'middle', 'end'] as const)[thirds.indexOf(Math.max(...thirds))] : null
  return { segments, where }
}

/** Route summary sent to ARIA (no per-cell arrays). */
export const routeSummary = (r: RouteResult, caution = 10) => {
  const { segments, where } = cautionStretches(r, caution)
  return {
    mode: r.mode, cells: r.cells, slope_max_deg: r.slope_max_deg, slope_mean_deg: r.slope_mean_deg,
    cells_above_caution: r.cells_above_caution, surface_length_3d_m: r.surface_length_3d_m,
    planimetric_length_m: r.planimetric_length_m, elevation_gain_m: r.elevation_gain_m,
    elevation_loss_m: r.elevation_loss_m, caution_segments: segments, caution_where: where,
    // Dune-crossing check from /api/route (app/context.py) — lets ARIA answer "Temperature on this path?".
    thermal: r.context?.thermal ?? null,
  }
}

export const askAssistant = (message: string, context: {
  current_lon?: number; current_lat?: number; dataset_id?: string; last_route?: ReturnType<typeof routeSummary> | null
}) =>
  fetch(`${BASE}/api/assistant/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  }).then(r => json<AssistantReply>(r))

// ---------------------------------------------------------------------------
// NASA Space Apps reference layers (static GeoJSON served by the backend)
// ---------------------------------------------------------------------------

/** USGS geologic map units (Tanaka et al. 2014, SIM 3292) — GET /api/geology/units. */
export interface GeologicUnitProps {
  unit: string; name: string; age: string; description: string; source: string; url: string; color?: string
}
export interface GeologicUnits {
  type: 'FeatureCollection'
  properties?: { caveat?: string; map?: string; url?: string }
  features: { type: 'Feature'; geometry: { type: 'Polygon'; coordinates: [number, number][][] }; properties: GeologicUnitProps }[]
}
export const getGeologicUnits = () =>
  fetch(`${BASE}/api/geology/units`).then(r => json<GeologicUnits>(r))

/** NASA's proposed Curiosity path up Mount Sharp — GET /api/curiosity/route. */
export interface CuriosityWaypoint { name: string; lon: number; lat: number; note: string }
export interface CuriosityRoute {
  type: 'FeatureCollection'
  features: {
    type: 'Feature'
    geometry: { type: 'LineString'; coordinates: [number, number][] }
    properties: { name: string; source: string; url: string; description: string; coordinate_note?: string; waypoints: CuriosityWaypoint[] }
  }[]
}
export const getCuriosityRoute = () =>
  fetch(`${BASE}/api/curiosity/route`).then(r => json<CuriosityRoute>(r))

/** NASA raw-image galleries linked from the site info cards. */
export const CURIOSITY_RAW_IMAGES = 'https://mars.nasa.gov/msl/multimedia/raw-images/'
export const MARS_TREK_URL = 'https://trek.nasa.gov/mars'
export const USGS_GEOLOGY_URL = 'https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars'
