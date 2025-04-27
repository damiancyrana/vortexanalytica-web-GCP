(() => {
    console.log("Quantum BG Script: Starting execution (Subtle Depth Effect)."); // Zmieniony log

    /* ────────── MOBILE NAV TOGGLE (bez zmian) ────────── */
    const btn = document.getElementById('mobileMenuBtn');
    const nav = document.getElementById('mainNav');
    if (btn && nav) {
        btn.addEventListener('click', () => { nav.classList.toggle('active'); btn.setAttribute('aria-expanded', String(nav.classList.contains('active'))); });
        document.addEventListener('click', ev => { if (nav.classList.contains('active') && !nav.contains(ev.target) && !btn.contains(ev.target)) { nav.classList.remove('active'); btn.setAttribute('aria-expanded', 'false'); } });
    } else {
        console.warn("Quantum BG Script: Mobile menu button or nav not found.");
    }

    /* ────────── THREE.JS BACKGROUND (SUBTLE DEPTH EFFECT) ────────── */
    if (typeof THREE === 'undefined') { console.error('Quantum BG Script: Three.js library not loaded.'); return; }
    const canvas = document.getElementById('quantum-field');
    if (!canvas) { console.error('Quantum BG Script: Canvas #quantum-field not found.'); return; }

    // Funkcje pomocnicze (bez zmian)
    const cssVar = (name, fallback = '#000000') => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    const cssColor = (name, fallback = '#000000') => {
        const colorValue = cssVar(name, fallback);
        try { return new THREE.Color(colorValue); }
        catch(e) { console.warn(`Quantum BG Script: Could not parse CSS var "${name}" (${colorValue}). Using ${fallback}.`); return new THREE.Color(fallback); }
    };

    // Deklaracje zmiennych - usunięto galaxyGroup i parametry galaktyki
    let scene, camera, renderer, clock;
    let backgroundStars;
    let targetCameraZ = 35;
    let currentFogColor = new THREE.Color();
    let backgroundColor = new THREE.Color();
    let starColor = new THREE.Color();
    let animationFrameId;

    // Parametry gwiazd - można dostosować dla większej subtelności
    const STARS_PARAMS = {
        count: 1500,        // Mniej gwiazd
        size: 0.06,         // Mniejsze gwiazdy
        range: 400,         // Nieco większy zasięg dla poczucia przestrzeni
        rotationSpeed: 0.005 // Bardzo wolna prędkość rotacji
    };

    // Budowanie tła gwiazd (bez zmian w logice, używa STARS_PARAMS)
    function buildBackgroundStars() {
        const vertices = [];
        for (let i = 0; i < STARS_PARAMS.count; i++) {
            vertices.push(
                (Math.random() - 0.5) * STARS_PARAMS.range,
                (Math.random() - 0.5) * STARS_PARAMS.range,
                (Math.random() - 0.5) * STARS_PARAMS.range
            );
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        const material = new THREE.PointsMaterial({
            size: STARS_PARAMS.size,
            sizeAttenuation: true, // Rozmiar maleje z odległością
            transparent: true,
            blending: THREE.AdditiveBlending, // Efekt "świetlistości"
            depthWrite: false // Zapobiega problemom z przezroczystością
        });
        const points = new THREE.Points(geometry, material);
        console.log("Quantum BG Script: Built background stars.");
        return points;
    }

    // Usunięto funkcję buildGalaxy()

    // Funkcja updateThemeColors (zmodyfikowana - usunięto logikę galaktyki)
    window.updateThemeColors = function() {
        const isDark = document.body.classList.contains('dark-theme');
        console.log(`Quantum BG Script: Updating theme colors. Is dark? ${isDark}`);

        // Aktualizacja koloru tła i mgły
        backgroundColor.copy(cssColor(isDark ? '--bg-dark' : '--bg-body-light', isDark ? '#0a0a10' : '#f0f2f5'));
        if (scene && scene.fog) {
            scene.fog.color.copy(backgroundColor);
        }

        // Aktualizacja koloru gwiazd
        starColor.copy(cssColor(isDark ? '--text-muted-dark' : '--text-muted-light', isDark ? '#555577' : '#aaaaaa'));
        if (backgroundStars && backgroundStars.material instanceof THREE.PointsMaterial) {
            backgroundStars.material.color.copy(starColor);
            // Dostosuj opacity dla subtelności
            backgroundStars.material.opacity = isDark ? 0.6 : 0.8; // Nieco jaśniejsze w trybie jasnym
            backgroundStars.material.needsUpdate = true;
            console.log(`Quantum BG Script: Background stars color set to ${starColor.getHexString()}, opacity ${backgroundStars.material.opacity}.`);
        }
    }

    // Funkcja init (zmodyfikowana - usunięto logikę galaktyki)
    function init() {
        console.log("Quantum BG Script: Initializing Three.js for Subtle Depth...");
        try {
            scene = new THREE.Scene();
            clock = new THREE.Clock();
            // Dostosuj pole widzenia i zakres kamery
            camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, STARS_PARAMS.range + 100); // Dalszy zakres
            camera.position.z = targetCameraZ;

            renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
            renderer.setClearColor(0x000000, 0);

            // Mgła dla efektu głębi - dostosuj gęstość wg potrzeb
            scene.fog = new THREE.FogExp2(currentFogColor, 0.008); // Nieco rzadsza mgła
            console.log("Quantum BG Script: Fog created with density 0.008.");

            // Dodaj tylko gwiazdy
            backgroundStars = buildBackgroundStars();
            scene.add(backgroundStars);

            // Usunięto dodawanie galaxyGroup

            scene.add(new THREE.AmbientLight(0xffffff, 0.1)); // Bardzo słabe światło otoczenia

            updateThemeColors(); // Ustaw kolory na starcie

            // Nasłuchiwacze (bez zmian)
            window.addEventListener('resize', onResize);
            document.body.addEventListener('wheel', onDocumentMouseWheel, { passive: true });
            const observer = new MutationObserver((mutationsList) => {
                mutationsList.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        console.log('Quantum BG Script: Body class change detected.');
                        updateThemeColors();
                    }
                });
            });
            observer.observe(document.body, { attributes: true });

            animate(); // Rozpocznij pętlę animacji
            console.log("Quantum BG Script: Initialization successful.");

        } catch (error) {
            console.error("Quantum BG Script: Error during Three.js initialization:", error);
            if (canvas) canvas.style.display = 'none';
        }
    }

    // Funkcja animate (zmodyfikowana - tylko rotacja gwiazd)
    function animate() {
        if (!renderer) {
            if (animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
            return;
        }
        animationFrameId = requestAnimationFrame(animate);

        try {
            const delta = clock.getDelta();
            const elapsedTime = clock.getElapsedTime(); // Użyjemy elapsedTime dla płynnej, ciągłej rotacji

            // Usunięto rotację galaxyGroup

            // Bardzo powolna, ciągła rotacja gwiazd tła dla iluzji ruchu
            if (backgroundStars) {
                // Obracaj bardzo powoli wokół osi Y i nieznacznie wokół X
                backgroundStars.rotation.y = elapsedTime * STARS_PARAMS.rotationSpeed;
                backgroundStars.rotation.x = elapsedTime * STARS_PARAMS.rotationSpeed * 0.5; // Wolniej wokół X
            }

            // Scroll zoom kamery (bez zmian)
            camera.position.z += (targetCameraZ - camera.position.z) * 0.04 * (delta * 60); // Płynne przejście zoomu

            // Usunięto camera.lookAt(0, 0, 0) - niepotrzebne dla statycznego tła

            renderer.render(scene, camera);

        } catch(error) {
            console.error("Quantum BG Script: Error during animation frame:", error);
            if(animationFrameId) { cancelAnimationFrame(animationFrameId); animationFrameId = null; }
        }
    }

    // Funkcje onResize i onDocumentMouseWheel (bez zmian)
    function onResize() {
        if (!camera || !renderer) return;
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
        console.log("Quantum BG Script: Resized.");
    }

    function onDocumentMouseWheel(event) {
        const zoomSensitivity = 0.01;
        const minZoom = 15; // Nieco dalszy minimalny zoom
        const maxZoom = 80; // Nieco dalszy maksymalny zoom
        targetCameraZ += event.deltaY * zoomSensitivity;
        targetCameraZ = Math.max(minZoom, Math.min(maxZoom, targetCameraZ));
    }

    // Inicjalizacja (bez zmian)
    init();

})();