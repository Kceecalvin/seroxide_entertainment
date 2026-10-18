import {
  AmbientLight, BufferGeometry, Color, DirectionalLight, Float32BufferAttribute,
  Group, Mesh, MeshStandardMaterial, PerspectiveCamera, Points, PointsMaterial,
  Scene, TorusGeometry, WebGLRenderer,
} from 'three';

/** Decorative, real WebGL orbit. Never required to browse or buy a ticket. */
export function mountScene(host: HTMLElement) {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  if (reduced.matches) return;
  let renderer: WebGLRenderer;
  try { renderer = new WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' }); }
  catch { host.dataset.webgl = 'unavailable'; return; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute('aria-hidden', 'true');
  host.appendChild(renderer.domElement);
  host.dataset.webgl = 'ready';
  const scene = new Scene();
  const camera = new PerspectiveCamera(38, 1, 0.1, 50);
  camera.position.z = 7.8;
  const group = new Group();
  scene.add(group, new AmbientLight(0xeecf8b, 2.4));
  const key = new DirectionalLight(0xffe9c9, 5);
  key.position.set(3, 5, 6);
  scene.add(key);
  const material = new MeshStandardMaterial({ color: new Color('#dcba78'), metalness: 0.66, roughness: 0.3, transparent: true, opacity: 0.64 });
  const rings: Mesh[] = [];
  for (let index = 0; index < 3; index++) {
    const ring = new Mesh(new TorusGeometry(2.1 + index * 0.12, index === 0 ? 0.015 : 0.006, 6, 120), material);
    ring.rotation.set(0.4 + index * 0.53, 0.4 + index * 0.5, 0.22);
    rings.push(ring);
    group.add(ring);
  }
  const positions: number[] = [];
  for (let i = 0; i < 70; i++) {
    const angle = i * Math.PI * 2 / 70;
    positions.push(Math.cos(angle) * 2.5, Math.sin(angle) * 2.9, Math.sin(angle * 3) * 0.5);
  }
  const pointsGeometry = new BufferGeometry();
  pointsGeometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  const pointsMaterial = new PointsMaterial({ color: '#f1cf8f', size: 0.017, transparent: true, opacity: 0.7 });
  group.add(new Points(pointsGeometry, pointsMaterial));
  const resize = () => {
    const { width, height } = host.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  };
  const resizer = new ResizeObserver(resize);
  resizer.observe(host);
  let visible = false;
  let disposed = false;
  let previousTime = 0;
  const draw = (time: number) => {
    if (time - previousTime < 32) return; // Decorative animation is capped at ~30 fps.
    previousTime = time;
    group.rotation.z = Math.sin(time * 0.0001) * 0.09;
    rings[0].rotation.y = 0.4 + Math.sin(time * 0.00015) * 0.18;
    rings[1].rotation.x = 0.93 + Math.cos(time * 0.0001) * 0.15;
    renderer.render(scene, camera);
  };
  const sync = () => {
    if (disposed) return;
    renderer.setAnimationLoop(visible && !document.hidden && !reduced.matches ? draw : null);
  };
  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); });
  observer.observe(host);
  document.addEventListener('visibilitychange', sync);
  reduced.addEventListener('change', sync);
  const contextLost = (event: Event) => { event.preventDefault(); renderer.setAnimationLoop(null); host.dataset.webgl = 'unavailable'; };
  const contextRestored = () => { host.dataset.webgl = 'ready'; resize(); sync(); };
  renderer.domElement.addEventListener('webglcontextlost', contextLost);
  renderer.domElement.addEventListener('webglcontextrestored', contextRestored);
  const dispose = (event: PageTransitionEvent) => {
    if (event.persisted) { renderer.setAnimationLoop(null); return; }
    disposed = true;
    renderer.setAnimationLoop(null);
    observer.disconnect();
    resizer.disconnect();
    document.removeEventListener('visibilitychange', sync);
    reduced.removeEventListener('change', sync);
    renderer.domElement.removeEventListener('webglcontextlost', contextLost);
    renderer.domElement.removeEventListener('webglcontextrestored', contextRestored);
    rings.forEach(ring => ring.geometry.dispose());
    material.dispose(); pointsGeometry.dispose(); pointsMaterial.dispose(); renderer.dispose();
    renderer.domElement.remove();
    window.removeEventListener('pageshow', sync);
  };
  window.addEventListener('pagehide', dispose, { once: true });
  window.addEventListener('pageshow', sync);
  resize();
}
