
(() => {
/* ────────── MOBILE NAV TOGGLE ────────── */
const btn = document.getElementById('mobileMenuBtn');
const nav = document.getElementById('mainNav');

if (btn && nav) {
    btn.addEventListener('click', () => {
    const active = nav.classList.toggle('active');
    btn.setAttribute('aria-expanded', String(active));
    });

    document.addEventListener('click', ev => {
    if (nav.classList.contains('active') &&
        !nav.contains(ev.target) &&
        !btn.contains(ev.target)) {
        nav.classList.remove('active');
        btn.setAttribute('aria-expanded', 'false');
    }
    });
}

/* ────────── THREE.JS BACKGROUND ────────── */
if (typeof THREE === 'undefined') {
    console.error('Three.js not loaded – quantum background disabled.');
    return;
}

/* Helpers */
const canvas = document.getElementById('quantum-field');
const cssColor = (name) =>
    new THREE.Color(
    getComputedStyle(document.documentElement)
        .getPropertyValue(name)
        .trim() || '#ffffff'
    );

/* Scene objects */
let scene, camera, renderer, clock, networkGroup;
let streamPaths = [];
const particles = [];

/* Build curved “data streams” */
function buildStreams(count = 10) {
    const paths = [];
    for (let i = 0; i < count; i++) {
    const pts = [];
    const steps = 15;
    for (let j = 0; j < steps; j++) {
        const t      = j / (steps - 1);
        const radius = 12 + Math.random() * 18;
        const angle  = (Math.random() - 0.5) * Math.PI * 3 + t * Math.PI * 1.5;
        const z      = (Math.random() - 0.5) * 50 +
                        Math.sin(t * Math.PI * 0.5) * 8;
        pts.push(new THREE.Vector3(
        radius * Math.cos(angle),
        radius * Math.sin(angle),
        z,
        ));
    }
    paths.push(new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.7));
    }
    return paths;
}

/* Create particle meshes */
function buildParticles(count = 120) {
    const matBlue = new THREE.MeshBasicMaterial({
    color: cssColor('--blue'), transparent: true, opacity: 0.6,
    });
    const matTeal = new THREE.MeshBasicMaterial({
    color: cssColor('--teal'), transparent: true, opacity: 0.6,
    });

    for (let i = 0; i < count; i++) {
    const geo  = new THREE.SphereGeometry(0.025 + Math.random() * 0.035, 5, 5);
    const mesh = new THREE.Mesh(
        geo,
        Math.random() < 0.85 ? matBlue.clone() : matTeal.clone()
    );

    const streamIndex = Math.floor(Math.random() * streamPaths.length);
    const position    = Math.random();

    mesh.userData = {
        streamIndex,
        position,
        speed: 0.0002 + Math.random() * 0.0008,
    };
    mesh.position.copy(streamPaths[streamIndex].getPointAt(position));

    particles.push(mesh);
    networkGroup.add(mesh);
    }
}

/* Init Three.js scene */
function init() {
    scene = new THREE.Scene();
    clock = new THREE.Clock();

    camera = new THREE.PerspectiveCamera(
    75, innerWidth / innerHeight, 0.1, 1000
    );
    camera.position.z = 30;

    renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true});
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    renderer.setClearColor(0x000000, 0);

    scene.add(new THREE.AmbientLight(0xffffff, 0.2));
    const dir = new THREE.DirectionalLight(0xffffff, 0.2);
    dir.position.set(5, 5, 5);
    scene.add(dir);

    networkGroup = new THREE.Group();
    scene.add(networkGroup);

    streamPaths = buildStreams();
    buildParticles();

    window.addEventListener('resize', onResize);
    animate();
}

/* Animation loop */
function animate() {
    requestAnimationFrame(animate);
    const delta = Math.min(clock.getDelta(), 0.1) * 60;

    networkGroup.rotation.y += 0.0001 * delta;
    networkGroup.rotation.x += 0.00005 * delta;

    particles.forEach(p => {
    const ud = p.userData;
    ud.position = (ud.position + ud.speed * delta) % 1;

    /* losowa zmiana ścieżki przy każdym pełnym okrążeniu */
    if (ud.position < ud.speed * delta && Math.random() < 0.05) {
        ud.streamIndex = (ud.streamIndex +
                        1 +
                        Math.floor(Math.random() * (streamPaths.length - 1))
                        ) % streamPaths.length;
    }
    p.position.copy(streamPaths[ud.streamIndex].getPointAt(ud.position));
    });

    renderer.render(scene, camera);
}

function onResize() {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
}

init();
})();
