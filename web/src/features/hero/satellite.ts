// Procedural Earth-observation satellite (variant A: gold bus, two solar wings, a dish) on a
// near-polar orbit over Colombia, plus its fading trail and orbit ring. Units: globe radius 100.
import {
  AdditiveBlending,
  AmbientLight,
  BoxGeometry,
  BufferGeometry,
  CircleGeometry,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  Euler,
  Float32BufferAttribute,
  Group,
  LatheGeometry,
  MathUtils,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  Object3D,
  PlaneGeometry,
  PMREMGenerator,
  Quaternion,
  ShaderMaterial,
  SphereGeometry,
  TorusGeometry,
  Vector2,
  Vector3,
  type Material,
  type Texture,
  type WebGLRenderer,
  type WebGLRenderTarget,
} from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";

import { GEO, GLOBE_RADIUS, ORBIT, SATELLITE, SUN, TRAIL, type QualityPreset } from "./config.ts";
import { SHOULDER_GLSL } from "./shaders.ts";
import {
  createCellTextures,
  createFoilTextures,
  createOsrTextures,
  mulberry32,
  yieldToBrowser,
  type FoilTextures,
} from "./textures.ts";

// ---------------------------------------------------------------------------------------------
// Orbit. The Earth is static, so the orbit is fixed in the Earth frame and every pass crosses
// Colombia. Frame: +Y north, longitude 0 on +Z, 90°E on +X (three-globe's convention).

const inclination = MathUtils.degToRad(ORBIT.inclinationDeg);
const centroidLat = MathUtils.degToRad(GEO.colombiaCentroid.lat);
// Argument of latitude over Colombia: the descending solution of sin(lat) = sin(i)·sin(u).
const colombiaAngle = Math.PI - Math.asin(Math.sin(centroidLat) / Math.sin(inclination));
// Longitude of the ascending node that puts that point on Colombia's centroid.
const nodeLng =
  MathUtils.degToRad(GEO.colombiaCentroid.lng) -
  Math.atan2(Math.cos(inclination) * Math.sin(colombiaAngle), Math.cos(colombiaAngle));
const equatorDirection = (lng: number) => new Vector3(Math.sin(lng), 0, Math.cos(lng));

/** Unit vector to the orbit's ascending node. */
export const ORBIT_NODE: Readonly<Vector3> = equatorDirection(nodeLng);
/** Unit vector 90° along the orbit from the node (towards the north at the node). */
export const ORBIT_QUADRATURE: Readonly<Vector3> = equatorDirection(nodeLng + Math.PI / 2)
  .multiplyScalar(Math.cos(inclination))
  .add(new Vector3(0, Math.sin(inclination), 0));
/** Unit orbit normal (the satellite's wing axis). */
export const ORBIT_NORMAL: Readonly<Vector3> = new Vector3()
  .crossVectors(ORBIT_NODE, ORBIT_QUADRATURE)
  .normalize();

/** Orbit angle (argument of latitude, radians) at which the satellite is over Colombia. */
export const COLOMBIA_ORBIT_ANGLE = colombiaAngle;

/**
 * Orbit angle at a scene time. A dual-harmonic warp slows the satellite down over Colombia and
 * speeds it up on the far side, while staying monotonic.
 *
 * @param timeS - Scene time in seconds.
 * @returns The argument of latitude in radians.
 */
export function orbitAngle(timeS: number): number {
  const phase = (timeS - ORBIT.peakTimeS) / ORBIT.periodS + 0.5;
  const p = phase - Math.floor(phase) - 0.5;
  const [first, second] = ORBIT.warp;
  const theta =
    2 * Math.PI * p - first * Math.sin(2 * Math.PI * p) + second * Math.sin(4 * Math.PI * p);
  return colombiaAngle + theta;
}

/**
 * Scene time within the first orbit at which the satellite is `offset` radians past Colombia
 * (negative: before the pass). Inverts the time warp numerically.
 *
 * @param offset - Orbit angle relative to the pass over Colombia, in radians.
 * @returns A scene time in seconds.
 */
export function timeForOrbitOffset(offset: number): number {
  let best = 0;
  let bestError = Number.POSITIVE_INFINITY;
  for (let t = 0; t < ORBIT.periodS; t += 0.005) {
    const delta = orbitAngle(t) - colombiaAngle - offset;
    const error = Math.abs(Math.atan2(Math.sin(delta), Math.cos(delta)));
    if (error < bestError) {
      bestError = error;
      best = t;
    }
  }
  return best;
}

/**
 * Unit vector from the Earth's center to the satellite at an orbit angle.
 *
 * @param angle - Argument of latitude in radians.
 * @param target - Receives the result.
 * @returns `target`.
 */
export function orbitDirection(angle: number, target: Vector3): Vector3 {
  return target
    .copy(ORBIT_NODE)
    .multiplyScalar(Math.cos(angle))
    .addScaledVector(ORBIT_QUADRATURE, Math.sin(angle));
}

/**
 * Unit direction of flight at an orbit angle.
 *
 * @param angle - Argument of latitude in radians.
 * @param target - Receives the result.
 * @returns `target`.
 */
export function orbitVelocityDirection(angle: number, target: Vector3): Vector3 {
  return target
    .copy(ORBIT_NODE)
    .multiplyScalar(-Math.sin(angle))
    .addScaledVector(ORBIT_QUADRATURE, Math.cos(angle));
}

// ---------------------------------------------------------------------------------------------
// Model building helpers.

type MaterialKey =
  | "gold"
  | "silver"
  | "osr"
  | "cells"
  | "panelBack"
  | "frame"
  | "titanium"
  | "anodize"
  | "aperture"
  | "lens"
  | "paint"
  | "cfrp";

type SatelliteMaterials = Readonly<Record<MaterialKey, Material>>;

const scratchQuaternion = new Quaternion();
const scratchPosition = new Vector3();
const scratchScale = new Vector3(1, 1, 1);
const UP = new Vector3(0, 1, 0);

function compose(position: Vector3, rotation: Euler | Quaternion = new Quaternion()): Matrix4 {
  const quaternion =
    rotation instanceof Quaternion ? rotation : scratchQuaternion.setFromEuler(rotation);
  return new Matrix4().compose(position, quaternion, scratchScale);
}

// Keeps only position, normal and uv, and drops the index, so parts can be merged.
function normalizeGeometry(geometry: BufferGeometry): BufferGeometry {
  const flat = geometry.index === null ? geometry.clone() : geometry.toNonIndexed();
  for (const name of Object.keys(flat.attributes)) {
    if (name !== "position" && name !== "normal" && name !== "uv") {
      flat.deleteAttribute(name);
    }
  }
  flat.clearGroups();
  return flat;
}

// Splits an indexed geometry into one non-indexed geometry per group, in group order.
function splitGroups(geometry: BufferGeometry): BufferGeometry[] {
  const flat = geometry.index === null ? geometry : geometry.toNonIndexed();
  const parts = geometry.groups.map((group) => {
    const part = new BufferGeometry();
    for (const name of ["position", "normal", "uv"]) {
      const attribute = flat.getAttribute(name);
      const size = attribute.itemSize;
      const array = attribute.array as Float32Array;
      part.setAttribute(
        name,
        new Float32BufferAttribute(
          array.slice(group.start * size, (group.start + group.count) * size),
          size,
        ),
      );
    }
    return part;
  });
  if (flat !== geometry) {
    flat.dispose();
  }
  geometry.dispose();
  return parts;
}

// Collects transformed parts per material and merges them into one mesh per material.
function createPartList() {
  const parts = new Map<MaterialKey, BufferGeometry[]>();
  return {
    add(key: MaterialKey, geometry: BufferGeometry, matrix?: Matrix4): void {
      const part = normalizeGeometry(geometry);
      geometry.dispose();
      if (matrix !== undefined) {
        part.applyMatrix4(matrix);
      }
      const list = parts.get(key) ?? [];
      list.push(part);
      parts.set(key, list);
    },
    build(name: string, materials: SatelliteMaterials): Group {
      const group = new Group();
      group.name = name;
      for (const [key, list] of parts) {
        const merged = mergeGeometries(list);
        for (const part of list) {
          part.dispose();
        }
        const mesh = new Mesh(merged, materials[key]);
        mesh.name = `${name}.${key}`;
        group.add(mesh);
      }
      parts.clear();
      return group;
    },
  };
}

// A cylinder from `from` to `to`.
function strut(from: Vector3, to: Vector3, radius: number, segments = 8): BufferGeometry {
  const direction = new Vector3().subVectors(to, from);
  const geometry = new CylinderGeometry(radius, radius, direction.length(), segments, 1, true);
  geometry.applyQuaternion(new Quaternion().setFromUnitVectors(UP, direction.normalize()));
  geometry.translate((from.x + to.x) / 2, (from.y + to.y) / 2, (from.z + to.z) / 2);
  return geometry;
}

// MLI blankets bulge between their taped edges: offset each face along its normal by
// a·(1 − u⁴)(1 − v⁴) and tilt the normals by the analytic gradient.
function createPillowedBox(
  width: number,
  height: number,
  depth: number,
  random: () => number,
): BoxGeometry {
  const geometry = new BoxGeometry(width, height, depth, 10, 9, 13);
  const positions = geometry.getAttribute("position");
  const normals = geometry.getAttribute("normal");
  const half = [width / 2, height / 2, depth / 2];
  const amplitudes = Array.from({ length: 6 }, () => 0.04 + 0.02 * random());
  const position = new Vector3();
  const normal = new Vector3();
  for (let i = 0; i < positions.count; i += 1) {
    position.fromBufferAttribute(positions, i);
    normal.fromBufferAttribute(normals, i);
    const axis = Math.abs(normal.x) > 0.5 ? 0 : Math.abs(normal.y) > 0.5 ? 1 : 2;
    const tangentAxes = [0, 1, 2].filter((a) => a !== axis);
    const [a1 = 0, a2 = 1] = tangentAxes;
    const h1 = half[a1] ?? 1;
    const h2 = half[a2] ?? 1;
    const u = position.getComponent(a1) / h1;
    const v = position.getComponent(a2) / h2;
    const faceIndex = axis * 2 + (normal.getComponent(axis) > 0 ? 0 : 1);
    const amplitude = amplitudes[faceIndex] ?? 0.05;
    const bulge = amplitude * (1 - u ** 4) * (1 - v ** 4);
    position.addScaledVector(normal, bulge);
    const slope1 = ((amplitude * -4 * u ** 3) / h1) * (1 - v ** 4);
    const slope2 = ((amplitude * -4 * v ** 3) / h2) * (1 - u ** 4);
    normal.setComponent(a1, -slope1).setComponent(a2, -slope2).normalize();
    positions.setXYZ(i, position.x, position.y, position.z);
    normals.setXYZ(i, normal.x, normal.y, normal.z);
  }
  return geometry;
}

// ---------------------------------------------------------------------------------------------
// Materials.

const SHOULDER_CACHE_KEY = "hero-satellite-shoulder";

// Soft luminance clamp before the opaque output, so the body never feeds the bloom pass.
function withShoulder<T extends Material>(material: T): T {
  const knee = SATELLITE.shoulderKnee.toFixed(3);
  const max = SATELLITE.shoulderMax.toFixed(3);
  material.onBeforeCompile = (shader) => {
    const source = shader.fragmentShader;
    const patched = source
      .replace("#include <common>", `#include <common>\n${SHOULDER_GLSL}`)
      .replace(
        "#include <opaque_fragment>",
        `outgoingLight = heroShoulder(outgoingLight, ${knee}, ${max});\n#include <opaque_fragment>`,
      );
    if (import.meta.env.DEV && !patched.includes("heroShoulder(outgoingLight")) {
      console.error("[hero] Satellite shoulder injection failed; three's shader chunks changed.");
    }
    shader.fragmentShader = patched;
  };
  material.customProgramCacheKey = () => SHOULDER_CACHE_KEY;
  return material;
}

interface SatelliteTextures {
  readonly all: readonly Texture[];
  readonly foil: FoilTextures;
  readonly silverFoil: {
    readonly normal: Texture;
    readonly orm: Texture;
    readonly albedo: Texture;
  };
  readonly cells: ReturnType<typeof createCellTextures>;
  readonly osr: ReturnType<typeof createOsrTextures>;
}

async function createSatelliteTextures(
  preset: QualityPreset,
  anisotropy: number,
  signal?: AbortSignal,
): Promise<SatelliteTextures> {
  await yieldToBrowser(signal);
  const foil = await createFoilTextures(preset.foil.size, preset.foil.creases, anisotropy, signal);
  // The silver blanket reuses the foil pattern, rotated and at a different scale.
  const silverFoil = {
    normal: foil.normal.clone(),
    orm: foil.orm.clone(),
    albedo: foil.albedo.clone(),
  };
  for (const texture of Object.values(silverFoil)) {
    texture.repeat.set(2.2, 2.2);
    texture.rotation = 0.6;
    texture.needsUpdate = true;
  }
  // Nothing has been uploaded to the GPU yet, so an abort here leaves no resources behind.
  await yieldToBrowser(signal);
  const cells = createCellTextures(preset.cells[0], preset.cells[1], anisotropy);
  await yieldToBrowser(signal);
  const osr = createOsrTextures(preset.osr, anisotropy);
  return {
    all: [
      foil.normal,
      foil.orm,
      foil.albedo,
      silverFoil.normal,
      silverFoil.orm,
      silverFoil.albedo,
      cells.albedo,
      cells.emissive,
      cells.normal,
      cells.orm,
      osr.normal,
      osr.orm,
    ],
    foil,
    silverFoil,
    cells,
    osr,
  };
}

function createMaterials(
  textures: SatelliteTextures,
  environment: Texture,
  preset: QualityPreset,
): SatelliteMaterials {
  const { colors } = SATELLITE;
  // Rotate the room so its brightest panels sit towards the sun.
  const environmentRotation = new Euler().setFromQuaternion(
    new Quaternion().setFromUnitVectors(UP, new Vector3(...SUN.dir).normalize()),
  );
  const pbr = <T extends MeshStandardMaterial>(material: T, envIntensity: number): T => {
    material.envMap = environment;
    material.envMapIntensity = envIntensity;
    material.envMapRotation.copy(environmentRotation);
    return withShoulder(material);
  };

  const foil = (color: string, maps: SatelliteTextures["silverFoil"]) =>
    pbr(
      new MeshPhysicalMaterial({
        color,
        metalness: 1,
        roughness: 1,
        map: maps.albedo,
        roughnessMap: maps.orm,
        aoMap: maps.orm,
        aoMapIntensity: 0.6,
        normalMap: maps.normal,
        normalScale: new Vector2(0.85, 0.85),
      }),
      0.55,
    );

  return {
    gold: foil(colors.gold, textures.foil),
    silver: foil(colors.silver, textures.silverFoil),
    osr: pbr(
      new MeshPhysicalMaterial({
        color: colors.osr,
        metalness: 1,
        roughness: 1,
        roughnessMap: textures.osr.orm,
        aoMap: textures.osr.orm,
        normalMap: textures.osr.normal,
        clearcoat: 1,
        clearcoatRoughness: 0.03,
      }),
      0.9,
    ),
    cells: pbr(
      new MeshPhysicalMaterial({
        color: 0xffffff,
        map: textures.cells.albedo,
        emissive: 0xffffff,
        emissiveMap: textures.cells.emissive,
        emissiveIntensity: 0.06,
        normalMap: textures.cells.normal,
        roughness: 1,
        metalness: 1,
        roughnessMap: textures.cells.orm,
        metalnessMap: textures.cells.orm,
        clearcoat: 1,
        clearcoatRoughness: 0.06,
        iridescence: preset.iridescence ? 0.35 : 0,
        iridescenceIOR: 2,
        iridescenceThicknessRange: [90, 140],
      }),
      // Space is black: keep the room's reflection faint so the cells stay deep blue.
      0.1,
    ),
    panelBack: pbr(
      new MeshStandardMaterial({ color: colors.panelBack, roughness: 0.45, metalness: 0.15 }),
      0.3,
    ),
    cfrp: pbr(
      new MeshStandardMaterial({ color: colors.panelBack, roughness: 0.4, metalness: 0.2 }),
      0.6,
    ),
    frame: pbr(
      new MeshStandardMaterial({ color: colors.frame, roughness: 0.3, metalness: 1 }),
      0.8,
    ),
    titanium: pbr(
      new MeshStandardMaterial({ color: colors.titanium, roughness: 0.38, metalness: 1 }),
      0.8,
    ),
    anodize: pbr(
      new MeshStandardMaterial({ color: colors.anodize, roughness: 0.55, metalness: 0.3 }),
      0.6,
    ),
    aperture: pbr(
      new MeshStandardMaterial({ color: colors.aperture, roughness: 1, metalness: 0 }),
      0,
    ),
    lens: pbr(
      new MeshPhysicalMaterial({
        color: colors.lens,
        roughness: 0.1,
        metalness: 0,
        clearcoat: 1,
        clearcoatRoughness: 0.02,
        iridescence: preset.iridescence ? 0.8 : 0,
      }),
      1,
    ),
    paint: pbr(
      new MeshStandardMaterial({ color: colors.paint, roughness: 0.62, metalness: 0 }),
      0.7,
    ),
  };
}

// ---------------------------------------------------------------------------------------------
// Model: bus, two wings and a dish, each a named node.

interface SatelliteModel {
  readonly root: Group;
  readonly wingArrays: readonly Group[];
  readonly beamAnchor: Object3D;
  readonly dishAzimuth: Group;
  readonly dishElevation: Group;
  readonly navLights: readonly Mesh[];
}

function buildBus(materials: SatelliteMaterials): { bus: Group; beamAnchor: Object3D } {
  const parts = createPartList();
  const random = mulberry32(0xb05);

  // Body: +X, −X, +Y, −Y, +Z faces in gold, the aft (−Z) face in silver.
  const body = splitGroups(createPillowedBox(4.0, 3.6, 5.2, random));
  body.forEach((face, index) => {
    parts.add(index === 5 ? "silver" : "gold", face);
  });

  // Nadir instrument and its dark aperture.
  parts.add("silver", new BoxGeometry(2.6, 1.3, 3.0, 4, 2, 4), compose(new Vector3(0, -2.45, 0.5)));
  parts.add("aperture", new BoxGeometry(1.8, 0.06, 0.55), compose(new Vector3(0, -3.11, 0.9)));

  // Radiator mirror on the zenith face.
  const radiator = new PlaneGeometry(3.4, 3.0);
  parts.add("osr", radiator, compose(new Vector3(0, 1.87, -0.8), new Euler(-Math.PI / 2, 0, 0)));

  // Two star trackers, canted out and aft: body, open baffle and lens.
  for (const side of [-1, 1]) {
    const mount = compose(
      new Vector3(1.25 * side, 1.95, -2.1),
      new Euler(MathUtils.degToRad(-15), 0, MathUtils.degToRad(-20 * side)),
    );
    parts.add("anodize", new CylinderGeometry(0.17, 0.17, 0.34, 16), mount);
    const baffle = new CylinderGeometry(0.3, 0.19, 0.44, 20, 1, true);
    baffle.translate(0, 0.39, 0);
    parts.add("anodize", baffle, mount);
    const lens = new CircleGeometry(0.12, 20);
    lens.rotateX(-Math.PI / 2);
    lens.translate(0, 0.18, 0);
    parts.add("lens", lens, mount);
  }

  // GPS patch antenna.
  parts.add(
    "paint",
    new CylinderGeometry(0.24, 0.24, 0.06, 20),
    compose(new Vector3(1.1, 1.9, 1.6)),
  );

  // Four thruster bells on the aft face.
  const bellProfile = [
    new Vector2(0.035, 0),
    new Vector2(0.05, 0.08),
    new Vector2(0.075, 0.18),
    new Vector2(0.11, 0.3),
  ];
  for (const x of [-1.5, 1.5]) {
    for (const y of [-1.3, 1.3]) {
      parts.add(
        "titanium",
        new LatheGeometry(bellProfile, 16),
        compose(new Vector3(x, y, -2.65), new Euler(-Math.PI / 2, 0, 0)),
      );
    }
  }

  // Launch adapter ring.
  const ringRotation = new Euler(Math.PI / 2, 0, 0);
  parts.add(
    "frame",
    new CylinderGeometry(1, 1, 0.16, 40, 1, true),
    compose(new Vector3(0, 0, -2.66), ringRotation),
  );
  parts.add("frame", new TorusGeometry(1, 0.04, 8, 40), compose(new Vector3(0, 0, -2.74)));

  const bus = parts.build("bus", materials);
  const beamAnchor = new Object3D();
  beamAnchor.name = "beamAnchor";
  beamAnchor.position.set(0, -3.15, 0.9);
  bus.add(beamAnchor);
  return { bus, beamAnchor };
}

function buildWing(
  direction: 1 | -1,
  materials: SatelliteMaterials,
): { wing: Group; array: Group; navLight: Mesh } {
  const name = direction === 1 ? "wingR" : "wingL";
  const wing = new Group();
  wing.name = name;
  wing.position.set(2.0 * direction, 0, 0);

  // Solar-array drive and its shaft.
  const drive = createPartList();
  const alongX = new Euler(0, 0, Math.PI / 2);
  drive.add(
    "titanium",
    new CylinderGeometry(0.32, 0.32, 0.4, 24),
    compose(new Vector3(0, 0, 0), alongX),
  );
  drive.add(
    "anodize",
    new CylinderGeometry(0.12, 0.12, 0.25, 12),
    compose(new Vector3(0.3 * direction, 0, 0), alongX),
  );
  wing.add(drive.build(`${name}.sada`, materials));

  const array = new Group();
  array.name = `${name}.array`;
  array.position.set(0.4 * direction, 0, 0);
  wing.add(array);

  const parts = createPartList();
  // Yoke: two struts converging on the drive, plus a cross tube at the first panel.
  const yokeX = 1.4 * direction;
  for (const z of [-0.9, 0.9]) {
    parts.add("cfrp", strut(new Vector3(0, 0, 0), new Vector3(yokeX, 0, z), 0.045));
  }
  parts.add("cfrp", strut(new Vector3(yokeX, 0, -1.15), new Vector3(yokeX, 0, 1.15), 0.05));

  // Four panels: cells on +Y, dark back on −Y, aluminium edges; proud bright frames on top.
  for (let i = 0; i < 4; i += 1) {
    const x = (2.4 + i * 2.07) * direction;
    const faces = splitGroups(new BoxGeometry(2.0, 0.045, 2.5));
    faces.forEach((face, index) => {
      const key: MaterialKey = index === 2 ? "cells" : index === 3 ? "panelBack" : "frame";
      parts.add(key, face, compose(new Vector3(x, 0, 0)));
    });
    const frameY = 0.0225 + 0.012;
    for (const z of [-1.22, 1.22]) {
      parts.add("frame", new BoxGeometry(2.0, 0.024, 0.06), compose(new Vector3(x, frameY, z)));
    }
    for (const dx of [-0.97, 0.97]) {
      parts.add(
        "frame",
        new BoxGeometry(0.06, 0.024, 2.5),
        compose(new Vector3(x + dx, frameY, 0)),
      );
    }
    if (i < 3) {
      for (const z of [-0.85, 0.85]) {
        parts.add(
          "titanium",
          new CylinderGeometry(0.035, 0.035, 0.12, 8),
          compose(new Vector3(x + 1.035 * direction, 0, z), alongX),
        );
      }
    }
  }
  array.add(parts.build(`${name}.panels`, materials));

  // Navigation light at the wingtip: red on the left wing, green on the right.
  const navLight = new Mesh(
    new SphereGeometry(0.08, 12, 8),
    new MeshBasicMaterial({ color: direction === 1 ? 0x34ff8a : 0xff3b30 }),
  );
  navLight.name = direction === 1 ? "navLight.green" : "navLight.red";
  navLight.position.set(9.66 * direction, 0.03, 1.2);
  array.add(navLight);

  return { wing, array, navLight };
}

function buildDish(materials: SatelliteMaterials): {
  dish: Group;
  azimuth: Group;
  elevation: Group;
} {
  const dish = new Group();
  dish.name = "dish";
  dish.position.set(-1.3, -1.8, 2.55);

  // Boom at 45° between nadir and ram.
  const boomAxis = new Vector3(0, -1, 1).normalize();
  const boomLength = 1.1;
  const boom = createPartList();
  boom.add(
    "cfrp",
    strut(new Vector3(0, 0, 0), boomAxis.clone().multiplyScalar(boomLength), 0.07, 10),
  );
  dish.add(boom.build("dish.boom", materials));

  // Gimbal frame: local +Y along the boom; azimuth turns about it, elevation tilts away from it.
  const mount = new Group();
  mount.name = "dish.mount";
  mount.position.copy(boomAxis).multiplyScalar(boomLength);
  mount.quaternion.setFromUnitVectors(UP, boomAxis);
  dish.add(mount);
  const azimuth = new Group();
  azimuth.name = "dish.az";
  mount.add(azimuth);
  const elevation = new Group();
  elevation.name = "dish.el";
  azimuth.add(elevation);

  const parts = createPartList();
  parts.add("titanium", new CylinderGeometry(0.12, 0.12, 0.18, 12));
  // Parabolic reflector y = r²/3.52 (focal length 0.88), white front and gold back.
  const focal = 0.88;
  const profile: Vector2[] = [];
  for (let i = 0; i <= 12; i += 1) {
    const r = (1.1 * i) / 12;
    profile.push(new Vector2(r, (r * r) / (4 * focal) + 0.15));
  }
  parts.add("paint", new LatheGeometry([...profile].reverse(), 48));
  const back = new LatheGeometry(
    profile.map((point) => new Vector2(point.x, point.y - 0.02)),
    48,
  );
  parts.add("gold", back);
  const rimY = (1.1 * 1.1) / (4 * focal) + 0.15;
  parts.add(
    "frame",
    new TorusGeometry(1.1, 0.03, 8, 48),
    compose(new Vector3(0, rimY, 0), new Euler(Math.PI / 2, 0, 0)),
  );
  // Feed struts and horn at the focus.
  const feed = new Vector3(0, focal + 0.15, 0);
  for (let k = 0; k < 3; k += 1) {
    const angle = (k * 2 * Math.PI) / 3;
    parts.add(
      "cfrp",
      strut(new Vector3(Math.cos(angle) * 1.08, rimY, Math.sin(angle) * 1.08), feed, 0.018, 6),
    );
  }
  parts.add(
    "titanium",
    new ConeGeometry(0.09, 0.2, 16, 1, true),
    compose(new Vector3(0, focal + 0.25, 0)),
  );
  elevation.add(parts.build("dish.reflector", materials));

  return { dish, azimuth, elevation };
}

function buildModel(materials: SatelliteMaterials): SatelliteModel {
  const root = new Group();
  root.name = "satellite";
  root.matrixAutoUpdate = false;

  const { bus, beamAnchor } = buildBus(materials);
  const left = buildWing(-1, materials);
  const right = buildWing(1, materials);
  const { dish, azimuth, elevation } = buildDish(materials);

  const strobe = new Mesh(
    new SphereGeometry(0.08, 12, 8),
    new MeshBasicMaterial({ color: 0xffffff }),
  );
  strobe.name = "navLight.strobe";
  strobe.position.set(0, 1.86, 1.9);
  bus.add(strobe);

  root.add(bus, left.wing, right.wing, dish);
  return {
    root,
    wingArrays: [left.array, right.array],
    beamAnchor,
    dishAzimuth: azimuth,
    dishElevation: elevation,
    navLights: [left.navLight, right.navLight, strobe],
  };
}

// ---------------------------------------------------------------------------------------------
// Orbit ring and trail: one ribbon expanded in screen space, no per-frame buffer writes.

const ribbonVertexShader = /* glsl */ `
uniform float uAngle;
uniform vec2 uResolution;
uniform float uPixelRatio;
uniform vec2 uWidth;
uniform vec3 uTrailShape; // decay, gap, length

attribute float aAngle;
attribute vec3 aTangent;
attribute float aSide;

varying float vTrail;
varying float vEdge;
varying float vHalfWidth;
varying float vNear;

void main() {
  float behind = mod(uAngle - aAngle + 6.2831853, 6.2831853);
  vTrail = exp(-behind / uTrailShape.x) * step(uTrailShape.y, behind) * step(behind, uTrailShape.z);

  vec4 clip = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  vec4 ahead = projectionMatrix * modelViewMatrix * vec4(position + aTangent, 1.0);
  vec2 halfResolution = 0.5 * uResolution;
  vec2 direction = normalize(ahead.xy / ahead.w * halfResolution - clip.xy / clip.w * halfResolution);
  vec2 normal = vec2(-direction.y, direction.x);

  // Half width in device pixels, plus half a pixel for the antialiased edge.
  vHalfWidth = 0.5 * mix(uWidth.x, uWidth.y, vTrail) * uPixelRatio + 0.5;
  vEdge = aSide * vHalfWidth;
  clip.xy += normal * vEdge / halfResolution * clip.w;
  gl_Position = clip;

  // Brighter on the arc that faces the camera.
  vNear = smoothstep(-0.2, 0.6, dot(normalize(position), normalize(cameraPosition)));
}
`;

const ribbonFragmentShader = /* glsl */ `
#include <common>

uniform vec3 uRingColor;
uniform vec2 uRingGain;
uniform vec3 uTrailColor;
uniform float uTrailGain;

varying float vTrail;
varying float vEdge;
varying float vHalfWidth;
varying float vNear;

void main() {
  float coverage = saturate(vHalfWidth - abs(vEdge));
  vec3 ring = uRingColor * (uRingGain.x + uRingGain.y * vNear);
  vec3 color = mix(ring, uTrailColor * uTrailGain, vTrail) * coverage;
  gl_FragColor = vec4(color, max(color.r, max(color.g, color.b)));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;

function createOrbitRibbon(samples: number): Mesh {
  const positions = new Float32Array(samples * 2 * 3);
  const tangents = new Float32Array(samples * 2 * 3);
  const angles = new Float32Array(samples * 2);
  const sides = new Float32Array(samples * 2);
  const point = new Vector3();
  const tangent = new Vector3();
  for (let i = 0; i < samples; i += 1) {
    const angle = (i / samples) * Math.PI * 2;
    orbitDirection(angle, point).multiplyScalar(ORBIT.radius);
    orbitVelocityDirection(angle, tangent);
    for (let side = 0; side < 2; side += 1) {
      const v = i * 2 + side;
      positions.set([point.x, point.y, point.z], v * 3);
      tangents.set([tangent.x, tangent.y, tangent.z], v * 3);
      angles[v] = angle;
      sides[v] = side === 0 ? -1 : 1;
    }
  }
  const indices: number[] = [];
  for (let i = 0; i < samples; i += 1) {
    const a = i * 2;
    const b = ((i + 1) % samples) * 2;
    // Counter-clockwise on screen: side +1 lies to the left of the direction of travel.
    indices.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
  geometry.setAttribute("aTangent", new Float32BufferAttribute(tangents, 3));
  geometry.setAttribute("aAngle", new Float32BufferAttribute(angles, 1));
  geometry.setAttribute("aSide", new Float32BufferAttribute(sides, 1));
  geometry.setIndex(indices);

  const material = new ShaderMaterial({
    name: "orbitRibbon",
    uniforms: {
      uAngle: { value: 0 },
      uResolution: { value: new Vector2(1, 1) },
      uPixelRatio: { value: 1 },
      uWidth: { value: new Vector2(...TRAIL.widthPx) },
      uTrailShape: { value: new Vector3(TRAIL.decay, TRAIL.gap, TRAIL.length) },
      uRingColor: { value: new Color(TRAIL.ringColor) },
      uRingGain: { value: new Vector2(...TRAIL.ringGain) },
      uTrailColor: { value: new Color(TRAIL.trailColor) },
      uTrailGain: { value: TRAIL.trailGain },
    },
    vertexShader: ribbonVertexShader,
    fragmentShader: ribbonFragmentShader,
    blending: AdditiveBlending,
    premultipliedAlpha: true,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new Mesh(geometry, material);
  mesh.name = "orbitRibbon";
  mesh.renderOrder = 8;
  mesh.frustumCulled = false;
  return mesh;
}

// ---------------------------------------------------------------------------------------------
// Rig: pose, solar-array drive, eclipse and lights, updated every frame.

/** Per-frame satellite state shared with the scan effect. */
export interface SatelliteState {
  /** Current orbit angle (radians). */
  angle: number;
  /** Unit vector from the Earth's center to the satellite. */
  readonly radial: Vector3;
  /** Satellite position (scene units). */
  readonly position: Vector3;
  /** Attitude: X = orbit normal (wings), Y = zenith, Z = direction of flight. */
  readonly attitude: Quaternion;
  /** World position of the sensor aperture, where the beam starts. */
  readonly aperture: Vector3;
  /** Current model scale. */
  scale: number;
}

/** The satellite, its lights and its orbit ribbon. */
export interface SatelliteRig {
  /** Add to the scene: the satellite, its lights and the orbit ribbon. */
  readonly objects: readonly Object3D[];
  /** Live state, updated by {@link SatelliteRig.update}. */
  readonly state: SatelliteState;
  /**
   * Advances the orbit and everything attached to it.
   *
   * @param timeS - Scene time in seconds.
   * @param dt - Frame time in seconds (already clamped).
   * @param cameraPosition - Current camera position, for the rim light.
   */
  readonly update: (timeS: number, dt: number, cameraPosition: Vector3) => void;
  /**
   * Re-derives the on-screen size after a resize.
   *
   * @param referenceCamera - Settled camera position (without intro, parallax or drift).
   * @param viewportHeight - Hero height in CSS pixels.
   * @param fovDeg - Vertical field of view in degrees.
   * @param drawingBuffer - Canvas size in device pixels.
   * @param pixelRatio - Device pixel ratio in use.
   */
  readonly setFraming: (
    referenceCamera: Vector3,
    viewportHeight: number,
    fovDeg: number,
    drawingBuffer: Vector2,
    pixelRatio: number,
  ) => void;
  /** Releases geometries, materials, textures and the environment map. */
  readonly dispose: () => void;
}

const sunDirection = new Vector3(...SUN.dir).normalize();
const radial = new Vector3();
const velocity = new Vector3();
const basis = new Matrix4();
const yaw = new Quaternion();
const toCamera = new Vector3();
const reference = new Vector3();

// Shortest signed angle from `from` to `to`.
function angleDelta(from: number, to: number): number {
  return Math.atan2(Math.sin(to - from), Math.cos(to - from));
}

/**
 * Builds the satellite rig: procedural textures (generated in slices), PBR materials lit by a
 * sun-aligned room environment, the model, its lights and the orbit ribbon.
 *
 * @param renderer - Renderer used for the environment map and texture limits.
 * @param preset - Quality preset.
 * @param signal - Aborts the build between texture slices (before anything touches the GPU).
 * @returns The rig, ready to add to the scene.
 */
export async function createSatellite(
  renderer: WebGLRenderer,
  preset: QualityPreset,
  signal?: AbortSignal,
): Promise<SatelliteRig> {
  const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const textures = await createSatelliteTextures(preset, anisotropy, signal);
  // The renderer may have been disposed while the textures were generated.
  signal?.throwIfAborted();

  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  let environment: WebGLRenderTarget;
  try {
    environment = pmrem.fromScene(room, SATELLITE.environmentBlur);
  } finally {
    room.dispose();
    pmrem.dispose();
  }

  const materials = createMaterials(textures, environment.texture, preset);
  const model = buildModel(materials);
  const ribbon = createOrbitRibbon(preset.ribbonSamples);
  const ribbonUniforms = (ribbon.material as ShaderMaterial).uniforms as {
    uAngle: { value: number };
    uResolution: { value: Vector2 };
    uPixelRatio: { value: number };
  };

  const { lights: lightConfig } = SATELLITE;
  const key = new DirectionalLight(lightConfig.keyColor, lightConfig.key);
  key.name = "satellite.keyLight";
  const rim = new DirectionalLight(lightConfig.rimColor, lightConfig.rim);
  rim.name = "satellite.rimLight";
  const earthshine = new DirectionalLight(lightConfig.earthshineColor, lightConfig.earthshine);
  earthshine.name = "satellite.earthshine";
  const ambient = new AmbientLight(lightConfig.ambientColor, lightConfig.ambient);
  ambient.name = "satellite.ambient";
  const aimedLights = [key, rim, earthshine] as const;

  const state: SatelliteState = {
    angle: 0,
    radial: new Vector3(),
    position: new Vector3(),
    attitude: new Quaternion(),
    aperture: new Vector3(),
    scale: 1,
  };

  let arrayAngle = 0;
  let arrayVelocity = 0;
  let initialized = false;
  const maxArrayRate = MathUtils.degToRad(SATELLITE.sada.maxDegPerS);

  function update(timeS: number, dt: number, cameraPosition: Vector3): void {
    const angle = orbitAngle(timeS);
    state.angle = angle;
    orbitDirection(angle, radial);
    orbitVelocityDirection(angle, velocity);
    state.radial.copy(radial);
    state.position.copy(radial).multiplyScalar(ORBIT.radius);

    // Nadir-pointing attitude: X = orbit normal (wings), Y = zenith, Z = ram; small yaw steering.
    basis.makeBasis(ORBIT_NORMAL, radial, velocity);
    model.root.quaternion.setFromRotationMatrix(basis);
    yaw.setFromAxisAngle(UP, MathUtils.degToRad(ORBIT.yawSteerDeg) * Math.sin(angle));
    model.root.quaternion.multiply(yaw);
    state.attitude.copy(model.root.quaternion);
    model.root.position.copy(state.position);
    model.root.scale.setScalar(state.scale);
    model.root.updateMatrix();
    // Updates the anchor's ancestors (including the root) before reading its world position.
    model.beamAnchor.getWorldPosition(state.aperture);

    // Solar arrays track the sun about the wing axis (critically damped, rate limited).
    const sunTrackAngle = Math.atan2(sunDirection.dot(velocity), sunDirection.dot(radial));
    if (!initialized) {
      arrayAngle = sunTrackAngle;
      initialized = true;
    }
    const { omega } = SATELLITE.sada;
    const error = angleDelta(arrayAngle, sunTrackAngle);
    arrayVelocity += (omega * omega * error - 2 * omega * arrayVelocity) * dt;
    arrayVelocity = MathUtils.clamp(arrayVelocity, -maxArrayRate, maxArrayRate);
    arrayAngle += arrayVelocity * dt;
    for (const array of model.wingArrays) {
      array.rotation.x = arrayAngle;
    }

    // Eclipse: the Earth's shadow is a cylinder behind it along the sun direction.
    const alongSun = state.position.dot(sunDirection);
    let shadow = 0;
    if (alongSun < 0) {
      const offAxis = reference
        .copy(sunDirection)
        .multiplyScalar(alongSun)
        .sub(state.position)
        .length();
      shadow = 1 - MathUtils.smoothstep(offAxis, GLOBE_RADIUS - 2, GLOBE_RADIUS + 2);
    }
    key.intensity = lightConfig.key * (1 - shadow);
    key.position.copy(state.position).addScaledVector(sunDirection, 50);
    key.target.position.copy(state.position);

    // Rim light from behind the satellite (as seen by the camera), slightly from above.
    toCamera.subVectors(state.position, cameraPosition).normalize();
    rim.position.copy(state.position).addScaledVector(toCamera, 50).addScaledVector(radial, 15);
    rim.target.position.copy(state.position);

    // Earthshine from below, only when the ground underneath is lit.
    earthshine.intensity =
      lightConfig.earthshine * MathUtils.smoothstep(radial.dot(sunDirection), -0.1, 0.5);
    earthshine.position.copy(state.position).addScaledVector(radial, -50);
    earthshine.target.position.copy(state.position);
    for (const light of aimedLights) {
      light.updateMatrixWorld();
      light.target.updateMatrixWorld();
    }

    ribbonUniforms.uAngle.value = angle;
  }

  function setFraming(
    referenceCamera: Vector3,
    viewportHeight: number,
    fovDeg: number,
    drawingBuffer: Vector2,
    pixelRatio: number,
  ): void {
    // Size the model so its span reads at the target pixel size over Colombia.
    orbitDirection(colombiaAngle, scratchPosition).multiplyScalar(ORBIT.radius);
    const distance = scratchPosition.distanceTo(referenceCamera);
    const pixelsPerUnit =
      viewportHeight / (2 * distance * Math.tan(MathUtils.degToRad(fovDeg / 2)));
    const [minScale, maxScale] = SATELLITE.scaleRange;
    state.scale = MathUtils.clamp(
      SATELLITE.targetSpanPx / (SATELLITE.spanUnits * pixelsPerUnit),
      minScale,
      maxScale,
    );
    ribbonUniforms.uResolution.value.copy(drawingBuffer);
    ribbonUniforms.uPixelRatio.value = pixelRatio;
  }

  return {
    objects: [
      model.root,
      ribbon,
      key,
      key.target,
      rim,
      rim.target,
      earthshine,
      earthshine.target,
      ambient,
    ],
    state,
    update,
    setFraming,
    dispose() {
      const disposedMaterials = new Set<Material>();
      model.root.traverse((object) => {
        if (object instanceof Mesh) {
          (object.geometry as BufferGeometry).dispose();
          const material = object.material as Material;
          if (!disposedMaterials.has(material)) {
            disposedMaterials.add(material);
            material.dispose();
          }
        }
      });
      ribbon.geometry.dispose();
      (ribbon.material as Material).dispose();
      for (const texture of textures.all) {
        texture.dispose();
      }
      environment.dispose();
      for (const light of aimedLights) {
        light.dispose();
      }
    },
  };
}
