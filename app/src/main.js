import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const viewport = document.getElementById('viewport');
const loading = document.getElementById('loading');
const loadText = document.getElementById('load-text');
const modeLabel = document.getElementById('mode-label');
const partLabel = document.getElementById('part-label');
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const models = {
  tibia: {
    20: {
      title: 'Большеберцовая кость на магнитах', short: 'большеберцовой кости', length: '400 мм', middle: '188 мм', reduction: '20 %',
      glb: './assets/tibia_magnetic.glb', threeMf: './assets/tibia_magnetic.3mf', magnets: '16', triangles: '12 640',
      construction: 'Вариант с серединой короче на 20 %. Средняя секция длиной 188 мм полая и разделена продольно на две половины. Восемь пар магнитов: четыре пары между половинами и четыре пары на поперечных стыках. Вокруг гнёзд расположены внутренние усиления.',
      camera: [.60,.40,.95], target: .20, mobileTarget: .235, explode: .06
    },
    30: {
      title: 'Большеберцовая кость на магнитах', short: 'большеберцовой кости', length: '400 мм', middle: '164,5 мм', reduction: '30 %',
      glb: './assets/tibia_magnetic_30.glb', threeMf: './assets/tibia_magnetic_30.3mf', magnets: '16', triangles: '12 488',
      construction: 'Вариант с серединой короче на 30 %. Средняя секция длиной 164,5 мм полая и разделена продольно на две половины. Восемь пар магнитов: четыре пары между половинами и четыре пары на поперечных стыках. Вокруг гнёзд расположены внутренние усиления.',
      camera: [.60,.40,.95], target: .20, mobileTarget: .235, explode: .06
    }
  },
  femur: {
    20: {
      title: 'Бедренная кость на магнитах', short: 'бедренной кости', length: '450 мм', middle: '212 мм', reduction: '20 %',
      glb: './assets/femur_magnetic.glb', threeMf: './assets/femur_magnetic.3mf', magnets: '16', triangles: '14 122',
      construction: 'Вариант с серединой короче на 20 %. Средняя секция длиной 212 мм полая и разделена продольно на две половины. Восемь пар магнитов: четыре пары между половинами и четыре пары на поперечных стыках. Вокруг гнёзд расположены внутренние усиления.',
      camera: [.67,.45,1.07], target: .225, mobileTarget: .28, explode: .065
    },
    30: {
      title: 'Бедренная кость на магнитах', short: 'бедренной кости', length: '450 мм', middle: '185,5 мм', reduction: '30 %',
      glb: './assets/femur_magnetic_30.glb', threeMf: './assets/femur_magnetic_30.3mf', magnets: '16', triangles: '13 998',
      construction: 'Вариант с серединой короче на 30 %. Средняя секция длиной 185,5 мм полая и разделена продольно на две половины. Восемь пар магнитов: четыре пары между половинами и четыре пары на поперечных стыках. Вокруг гнёзд расположены внутренние усиления.',
      camera: [.67,.45,1.07], target: .225, mobileTarget: .28, explode: .065
    }
  }
};
function parseHash() {
  const match = location.hash.match(/^#(tibia|femur)(?:-(20|30))?$/);
  return { model: match?.[1] || 'tibia', version: match?.[2] || '20' };
}
let { model: currentModel, version: currentVersion } = parseHash();
let loadToken = 0;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x293536);
const camera = new THREE.PerspectiveCamera(32, 1, 0.005, 20);
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.08;
viewport.prepend(renderer.domElement);

scene.add(new THREE.HemisphereLight(0xf4eee2, 0x506165, 2.1));
const key = new THREE.DirectionalLight(0xfff4df, 3.0); key.position.set(0.4, 0.7, 0.6); scene.add(key);
const fill = new THREE.DirectionalLight(0xc9e1e4, 1.3); fill.position.set(-0.5, 0.25, -0.4); scene.add(fill);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = .07;
controls.minDistance = .3; controls.maxDistance = 2;
controls.enablePan = true;

function resetCamera() {
  const cfg = models[currentModel][currentVersion];
  camera.position.set(...cfg.camera);
  controls.target.set(0, viewport.clientWidth < 600 ? cfg.mobileTarget : cfg.target, 0);
  controls.update();
}

function resize() {
  const w = viewport.clientWidth, h = viewport.clientHeight;
  if (!w || !h) return;
  camera.aspect = w / h; camera.updateProjectionMatrix(); renderer.setSize(w, h, false);
}
new ResizeObserver(resize).observe(viewport); resize(); resetCamera();

const parts = {};
const targets = {};
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let selected = null;
let animating = false;

const names = {
  lower: '01_Нижняя_секция', a: '02_Средняя_половина_A',
  b: '03_Средняя_половина_B', upper: '04_Верхняя_секция'
};
const stateText = {
  exploded: 'Разобранный вид', 1: 'Шаг 1 · соединение половин',
  2: 'Шаг 2 · установка нижней секции', 3: 'Шаг 3 · установка верхней секции', assembled: 'Полностью собрано'
};
const offsets = {
  exploded: { lower: [0,-.06,0], a: [0,0,.05], b: [0,0,-.05], upper: [0,.06,0] },
  assembled: { lower: [0,0,0], a: [0,0,0], b: [0,0,0], upper: [0,0,0] }
};
offsets[1] = offsets.assembled; offsets[2] = offsets.assembled; offsets[3] = offsets.assembled;

function selectPart(mesh) {
  if (selected && selected !== mesh) {
    selected.material.emissive.setHex(0x000000); selected.material.emissiveIntensity = 0;
  }
  selected = mesh;
  if (mesh) {
    mesh.material.emissive.setHex(0x6b3826); mesh.material.emissiveIntensity = .34;
    partLabel.textContent = mesh.name;
  } else partLabel.textContent = 'Выберите деталь щелчком';
}

function setState(state) {
  if (Object.keys(parts).length !== 4) return;
  const visible = state === 'exploded' || state === 'assembled' ? ['lower','a','b','upper'] :
    state === 1 ? ['a','b'] : state === 2 ? ['lower','a','b'] : ['lower','a','b','upper'];
  Object.entries(parts).forEach(([key, mesh]) => {
    mesh.visible = visible.includes(key);
    targets[key].set(...offsets[state][key]);
  });
  if (reducedMotion) {
    Object.entries(parts).forEach(([key, mesh]) => mesh.position.copy(targets[key]));
  }
  animating = !reducedMotion;
  modeLabel.textContent = stateText[state];
  document.querySelectorAll('[data-step],#exploded,#assembled').forEach(btn => {
    const active = btn.dataset.step ? Number(btn.dataset.step) === state : btn.id === state;
    btn.classList.toggle('active', active); btn.setAttribute('aria-pressed', String(active));
  });
  selectPart(null);
}

function updateModelUI(cfg) {
  document.getElementById('model-title').textContent = cfg.title;
  document.getElementById('model-length').textContent = cfg.length;
  document.getElementById('spec-magnets').textContent = cfg.magnets;
  document.getElementById('spec-middle').textContent = cfg.middle;
  document.getElementById('spec-version').textContent = cfg.reduction;
  document.getElementById('spec-triangles').textContent = cfg.triangles;
  document.getElementById('construction-text').textContent = cfg.construction;
  document.getElementById('source-text').textContent = `Изменения для ${cfg.short}: масштаб ${cfg.length}, выравнивание оси, разделение, полость, усиления и магнитные посадки.`;
  document.getElementById('download-3mf').href = cfg.threeMf;
  document.getElementById('download-glb').href = cfg.glb;
  document.querySelectorAll('[data-model]').forEach(btn => {
    const active = btn.dataset.model === currentModel;
    btn.classList.toggle('active', active); btn.setAttribute('aria-pressed', String(active));
  });
  document.querySelectorAll('button[data-version]').forEach(btn => {
    const active = btn.dataset.version === currentVersion;
    btn.classList.toggle('active', active); btn.setAttribute('aria-pressed', String(active));
  });
}

function clearParts() {
  Object.values(parts).forEach(mesh => {
    scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose();
    delete targets[Object.keys(parts).find(k => parts[k] === mesh)];
  });
  Object.keys(parts).forEach(k => delete parts[k]);
  selectPart(null);
}

const loader = new GLTFLoader();
function loadModel(modelKey, versionKey = currentVersion) {
  if (!models[modelKey]?.[versionKey]) return;
  currentModel = modelKey;
  currentVersion = versionKey;
  const cfg = models[modelKey][versionKey];
  const token = ++loadToken;
  clearParts();
  updateModelUI(cfg);
  resetCamera();
  loading.classList.remove('hidden');
  loadText.textContent = 'Загрузка анатомической модели…';
  document.documentElement.dataset.modelReady = 'false';
  document.documentElement.dataset.model = modelKey;
  document.documentElement.dataset.version = versionKey;
  const e = cfg.explode;
  offsets.exploded = { lower:[0,-e,0], a:[0,0,e], b:[0,0,-e], upper:[0,e,0] };

  loader.load(cfg.glb, gltf => {
    if (token !== loadToken) return;
    const meshes = [];
    gltf.scene.traverse(obj => { if (obj.isMesh) meshes.push(obj); });
    meshes.forEach(obj => {
      const partKey = Object.keys(names).find(k => names[k] === obj.name);
      if (!partKey) return;
      obj.material = obj.material.clone();
      obj.material.roughness = .46;
      parts[partKey] = obj; targets[partKey] = new THREE.Vector3();
      scene.add(obj);
    });
    if (Object.keys(parts).length !== 4) throw new Error('В GLB не найдены все четыре детали');
    Object.entries(parts).forEach(([partKey, mesh]) => mesh.position.set(...offsets.exploded[partKey]));
    resetCamera();
    setState('exploded');
    loading.classList.add('hidden');
    document.documentElement.dataset.modelReady = 'true';
  }, progress => {
    if (token === loadToken && progress.total) loadText.textContent = `Загрузка модели… ${Math.round(progress.loaded / progress.total * 100)}%`;
  }, error => {
    if (token !== loadToken) return;
    console.error(error);
    loadText.textContent = 'Не удалось загрузить 3D-модель. Скачайте GLB или 3MF по ссылкам рядом.';
  });
}

let down = null;
renderer.domElement.addEventListener('pointerdown', e => { down = { x:e.clientX, y:e.clientY }; });
renderer.domElement.addEventListener('pointerup', e => {
  if (!down || Math.hypot(e.clientX-down.x, e.clientY-down.y) > 5) return;
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.set((e.clientX-rect.left)/rect.width*2-1, -(e.clientY-rect.top)/rect.height*2+1);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(Object.values(parts).filter(m => m.visible), false);
  selectPart(hits.length ? hits[0].object : null);
});

document.getElementById('exploded').addEventListener('click', () => setState('exploded'));
document.getElementById('assembled').addEventListener('click', () => setState('assembled'));
document.querySelectorAll('[data-step]').forEach(btn => btn.addEventListener('click', () => setState(Number(btn.dataset.step))));
document.getElementById('reset-view').addEventListener('click', resetCamera);
document.querySelectorAll('[data-model]').forEach(btn => btn.addEventListener('click', () => {
  const next = btn.dataset.model;
  history.replaceState(null, '', `#${next}-${currentVersion}`);
  if (next !== currentModel || document.documentElement.dataset.modelReady !== 'true') loadModel(next, currentVersion);
}));
document.querySelectorAll('button[data-version]').forEach(btn => btn.addEventListener('click', () => {
  const next = btn.dataset.version;
  history.replaceState(null, '', `#${currentModel}-${next}`);
  if (next !== currentVersion || document.documentElement.dataset.modelReady !== 'true') loadModel(currentModel, next);
}));
window.addEventListener('hashchange', () => {
  const next = parseHash();
  if (next.model !== currentModel || next.version !== currentVersion) loadModel(next.model, next.version);
});
viewport.addEventListener('keydown', e => {
  if (e.key === '0') setState('exploded');
  if (['1','2','3'].includes(e.key)) setState(Number(e.key));
  if (e.key === '4') setState('assembled');
  if (e.key.toLowerCase() === 'r') resetCamera();
});

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), .05);
  if (animating) {
    let moving = false;
    const alpha = 1 - Math.exp(-10 * dt);
    Object.entries(parts).forEach(([partKey, mesh]) => {
      if (mesh.position.distanceTo(targets[partKey]) > .00005) moving = true;
      mesh.position.lerp(targets[partKey], alpha);
    });
    if (!moving) {
      Object.entries(parts).forEach(([partKey, mesh]) => mesh.position.copy(targets[partKey]));
      animating = false;
    }
  }
  controls.update(); renderer.render(scene, camera);
}
loadModel(currentModel, currentVersion);
animate();
