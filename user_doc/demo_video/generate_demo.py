"""
Script d'automatisation de démonstration vidéo - Projet Klepsydrix

Ce script permet de générer une vidéo de démonstration (1 à 2 minutes) en combinant :
1. Narration audio (Kokoro TTS, local et gratuit)
2. Capture vidéo automatisée (Playwright), pilotant le frontend Klepsydrix (Vue + Vite)
   connecté au backend FastAPI, sur la base de démonstration seedée par
   backend/app/core/init_demo.py
3. Montage automatique (MoviePy)

ETAPES DE LA PRODUCION APPUYEE SUR UN LLM :
--------------------------------------------
Pré-requis : l'application est développée, le jeu de données de démo existe
(base "timetable" seedée via `backend/.venv/bin/python -m backend.app.core.init_demo`),
la documentation du projet est rédigée (voir user_doc/chef_etablissement_doc.md).

1. Envoyer au LLM la documentation du projet : "J'ai construit une web app (frontend Vue +
backend FastAPI) qui permet de construire l'emploi du temps annuel d'un établissement scolaire.
Je veux générer une vidéo de démonstration de 1 à 2 minutes avec une voix off en français. Voici
la documentation du projet en PJ. Rédige moi le tableau de minutage de la démonstration avec les
3 colonnes suivantes : 1/ le minutage 2/ l'action à réaliser visuellement par l'utilisateur
3/ le texte de la voix off "

2. Envoyer au LLM le tableau de minutage généré par le LLM, ainsi que ce script,
et lui demander : "Voici le tableau de minutage, adapte le script python ci-joint
pour qu'il corresponde au tableau de minutage et aux actions à réaliser.
Les sélecteurs CSS doivent être des placeholder à remplacer par les vrais "clics" à
l'étape suivante."

3. Envoyer au LLM : "Voici le script de génération vidéo, ainsi que les fichiers Vue de
l'application ciblée par la démo (ou le script frontend/scripts/doc-screenshots/lib.mjs
qui contient déjà les sélecteurs vérifiés). Adapte le script pour intégrer les sélecteurs
CSS et les actions à réaliser."

INSTALLATION DES DEPENDANCES :
------------------------------
# Dépendances système : ffmpeg (requis par MoviePy), polices DejaVu (page de garde)
sudo apt update && sudo apt install -y python3-pip python3-venv ffmpeg fonts-dejavu-core

# Dépendances Python (kokoro-onnx: TTS local léger, aucune dépendance Cython)
pip install playwright moviepy kokoro-onnx soundfile pillow requests --break-system-packages

# Navigateur Chromium pour Playwright + ses dépendances système
playwright install --with-deps chromium


EXECUTION DU SCRIPT :
---------------------
# Pré-requis : backend + frontend démarrés (./start_services.sh start) et base de démo seedée
python3 generate_demo.py

# Mode montage seul (réutilise la dernière capture vidéo, ne relance pas Playwright)
python3 generate_demo.py --assemble-only



STRUCTURE DU SCRIPT :
--------------------
- CONFIGURATION : URL locale du frontend Klepsydrix, identifiants du compte de démo
  (mêmes conventions que frontend/scripts/doc-screenshots/lib.mjs), réglages Kokoro.
- AUDIO : Génération des segments WAV à partir du dictionnaire 'script_segments'
          via Kokoro (aucune clé API, aucun quota).
- CAPTURE :
    - Injection d'un curseur rouge (JS) pour la visibilité des clics.
    - SyncNarrator : Classe assurant que l'audio et la vidéo restent synchronisés.
    - open_tree_path : portage Python de frontend/scripts/doc-screenshots/lib.mjs::openTreePath,
      pour naviguer dans l'arborescence de gauche (NotebooksTree.vue) par libellés affichés.
    - Logique métier : Parcours utilisateur automatisé dans Klepsydrix (connexion, grille EDT,
      classes, enseignants, cours, TRMD, comptes & droits).
- MONTAGE :
    - create_title_card : Génère une slide d'intro.
    - assemble : Assemble les clips et mixe l'audio en respectant les timestamps réels.

"""
import os
import asyncio
import time
import subprocess
import sys
import hashlib
import json
import socket
from datetime import datetime
from pathlib import Path

import moviepy as mp
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION GÉNÉRALE ---
BASE_DIR = Path(__file__).parent.absolute()
ROOT_DIR = BASE_DIR.parent
AUDIO_DIR = BASE_DIR / "temp_audio"
VIDEO_DIR = BASE_DIR / "temp_video"
AUDIO_DIR.mkdir(exist_ok=True)
VIDEO_DIR.mkdir(exist_ok=True)

BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"

# Klepsydrix est une app client-serveur (frontend Vite + backend FastAPI) : les deux services
# doivent tourner avant la capture. Mêmes conventions que start_services.sh et
# frontend/scripts/doc-screenshots/lib.mjs (BASE_URL, compte et base de démo).
BASE_URL = os.environ.get("KLEPSYDRIX_BASE_URL", "http://localhost:3000")
BACKEND_URL = "http://localhost:8000"
DEMO_DB = "timetable"
DEMO_IDENTIFIER = "demo@klepsydrix.fr"
DEMO_PASSWORD = "Demo1234!"

# --- CONFIGURATION DE L'APPLICATION (page de garde) ---
APP_SETTINGS = {
    "title": "Klepsydrix",
    "subtitle": "L'emploi du temps annuel de l'établissement,\nconstruit et tenu à jour ensemble",
    "bg_color": (255, 255, 255),     # Blanc
    "accent_color": (99, 102, 241),  # Indigo #6366f1 (--accent-primary, frontend/src/assets/main.css)
    "footer_tagline": "Grille EDT • Classes • Enseignants • TRMD • Comptes & droits",
    # Backend FastAPI + frontend Vite à démarrer avant la capture (voir start_services.sh).
    "services": [
        {
            "name": "backend",
            "port": 8000,
            "check_url": f"{BACKEND_URL}/",
            "cmd": ["bash", "-c", f"PYTHONPATH={ROOT_DIR} {BACKEND_DIR}/.venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"],
            "cwd": ROOT_DIR,
        },
        {
            "name": "frontend",
            "port": 3000,
            "check_url": BASE_URL,
            "cmd": ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"],
            "cwd": FRONTEND_DIR,
        },
    ],
}

# --- CONFIGURATION KOKORO ONNX (TTS local, gratuit) ---
KOKORO_LANG = "fr-fr"        # Langue : "en-us", "en-gb", "fr-fr"...
KOKORO_VOICE = "ff_siwis"    # Voix : "ff_siwis" (FR-FR), "am_adam" (EN-US), "af_bella" (EN-US)...
KOKORO_SAMPLE_RATE = 24000

# --- SEGMENTS DE VOIX OFF (script de la démo) ---
script_segments = [
    {
        "id": "01_intro",
        "text": "Découvrez Klepsydrix, une plateforme web pour construire l'emploi du temps annuel d'un établissement scolaire, des classes et des équipes enseignantes jusqu'à la grille finale, tenue à jour au fil des évolutions."
    },
    {
        "id": "02_login",
        "text": "Tout commence par une connexion simple et sécurisée. Chaque établissement travaille dans sa propre base, si bien que les données restent totalement séparées d'un établissement à l'autre."
    },
    {
        "id": "03_timetable_grid",
        "text": "L'écran d'accueil, c'est la grille de l'emploi du temps elle-même, avec les cours restant à placer listés sur le côté, prêts à être positionnés."
    },
    {
        "id": "04_divisions",
        "text": "Dans Emploi du temps, la rubrique Classes liste toutes les divisions de l'établissement, avec leur effectif et leur découpage en groupes."
    },
    {
        "id": "05_preferences",
        "text": "Chaque classe porte aussi ses propres vœux et contraintes, comme des créneaux libres préférés, que le moteur de calcul prend en compte pour construire l'emploi du temps."
    },
    {
        "id": "06_teachers_courses",
        "text": "La liste des enseignants réunit chaque professeur avec ses matières, tandis que la liste des cours affiche chaque service : matière, classe, volume horaire et enseignant."
    },
    {
        "id": "07_trmd",
        "text": "Avant même la rentrée, la synthèse TRMD permet aux équipes de direction de vérifier que les heures d'enseignement sont bien réparties entre matières et personnels."
    },
    {
        "id": "08_accounts_outro",
        "text": "Et dans les paramètres, l'établissement gère les comptes utilisateurs et les droits d'accès de toute l'équipe. Klepsydrix : l'emploi du temps annuel, en toute simplicité."
    },
]


# --- SERVICES ---
def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_service(service_config):
    import requests
    name = service_config["name"]
    port = service_config["port"]
    url = service_config.get("check_url")

    print(f"⏳ Attente de {name} sur le port {port}...")
    for i in range(40):
        if is_port_open(port):
            if url:
                try:
                    resp = requests.get(url, timeout=2)
                    if resp.status_code == 200:
                        print(f"  ✅ {name} opérationnel.")
                        return True
                except Exception:
                    pass
            else:
                print(f"  ✅ {name} (port ouvert).")
                return True

        if i % 5 == 0:
            print(f"🚀 [Tentative {i // 5 + 1}] Lancement de {name}...")
            subprocess.Popen(
                service_config["cmd"],
                cwd=str(service_config["cwd"]),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        time.sleep(3)
    return False


# --- AUDIO (Kokoro ONNX, local, gratuit) ---
def generate_audio():
    print("🎙️ Phase Audio Kokoro ONNX (local, gratuit, sans clé API)...")
    try:
        from kokoro_onnx import Kokoro
        import soundfile as sf
        kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    except Exception as e:
        print(f"  ❌ Erreur import Kokoro ONNX : {e}")
        print("     -> pip install kokoro-onnx soundfile")
        print("     -> wget https://github.com/thewhitetulip/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx")
        print("     -> wget https://github.com/thewhitetulip/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin")
        return {s['id']: 5.0 for s in script_segments}, {}

    durations = {}
    paths_map = {}
    for segment in script_segments:
        text_hash = hashlib.md5(segment['text'].encode()).hexdigest()
        path = AUDIO_DIR / f"{segment['id']}_{text_hash}.wav"

        # Nettoyage des anciens fichiers pour cet ID si le texte a changé
        for old_file in AUDIO_DIR.glob(f"{segment['id']}_*.wav"):
            if old_file.name != path.name:
                old_file.unlink()

        if path.exists() and path.stat().st_size > 0:
            try:
                info = sf.info(str(path))
                durations[segment['id']] = info.frames / info.samplerate
                paths_map[segment['id']] = path
                print(f"  ✅ {segment['id']} (cache : {durations[segment['id']]:.1f}s)")
                continue
            except Exception:
                pass

        print(f"  🎙️ Génération {segment['id']} (nouveau texte détecté)")
        try:
            samples, sample_rate = kokoro.create(segment['text'], voice=KOKORO_VOICE, lang=KOKORO_LANG)
            sf.write(str(path), samples, sample_rate)
            durations[segment['id']] = len(samples) / sample_rate
            paths_map[segment['id']] = path
            print(f"    -> OK ({durations[segment['id']]:.1f}s)")
        except Exception as e:
            print(f"    ❌ Échec : {e}")
            durations[segment['id']] = 5.0
    return durations, paths_map


# --- UTILITAIRES CAPTURE ---
async def install_cursor(page):
    """Injections du code JS pour le curseur (définition des fonctions et style)."""
    js_code = """
    window.setupFakeCursor = function() {
        if (document.getElementById('fake-cursor')) return;
        const cursor = document.createElement('div');
        cursor.id = 'fake-cursor';
        cursor.style.position = 'absolute';
        cursor.style.zIndex = '99999';
        cursor.style.width = '20px';
        cursor.style.height = '20px';
        cursor.style.borderRadius = '50%';
        cursor.style.backgroundColor = 'red';
        cursor.style.border = '2px solid white';
        cursor.style.pointerEvents = 'none';
        cursor.style.transition = 'all 0.5s ease-out';
        cursor.style.boxShadow = '0 0 10px rgba(0,0,0,0.5)';
        cursor.style.left = '0px';
        cursor.style.top = '0px';
        document.body.appendChild(cursor);

        window.moveCursor = (x, y) => {
          cursor.style.left = (x - 10) + 'px';
          cursor.style.top = (y - 10) + 'px';
        };

        window.clickCursor = () => {
          cursor.style.transform = 'scale(0.8)';
          cursor.style.backgroundColor = 'orange';
          setTimeout(() => {
            cursor.style.transform = 'scale(1)';
            cursor.style.backgroundColor = 'red';
          }, 200);
        };
    };
    window.setupFakeCursor();
    """
    await page.add_init_script(js_code)
    try:
        await page.evaluate(js_code)
    except Exception:
        pass


async def move_cursor(page, selector=None, x=None, y=None):
    """Déplace le pointeur rouge vers un élément ou des coordonnées."""
    await page.evaluate("if(window.setupFakeCursor) window.setupFakeCursor();")

    if selector:
        try:
            box = await page.locator(selector).first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
        except Exception:
            pass

    if x is not None and y is not None:
        try:
            await page.evaluate(f"if(window.moveCursor) window.moveCursor({x}, {y})")
            await asyncio.sleep(0.6)
        except Exception:
            pass


async def move_cursor_to_locator(page, locator):
    """Déplace le curseur vers un Locator déjà résolu (utile après un .filter()/hasText)."""
    try:
        box = await locator.bounding_box()
        if box:
            await move_cursor(page, None, box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    except Exception:
        pass


async def open_tree_path(page, titles, animate=True):
    """Portage Python de frontend/scripts/doc-screenshots/lib.mjs::openTreePath.

    Ouvre un chemin dans l'arborescence de gauche (NotebooksTree.vue) par les libellés
    affichés, ex. open_tree_path(page, ["Emploi du temps", "Classes", "Liste"]).
    """
    l1_title = titles[0]
    l2_title = titles[1] if len(titles) > 1 else None
    l3_title = titles[2] if len(titles) > 2 else None

    l1_header = page.locator(".nav-group-header", has_text=l1_title).first
    await l1_header.wait_for(state="visible")
    if animate:
        await move_cursor_to_locator(page, l1_header)
        await page.evaluate("window.clickCursor()")
    l1_class = await l1_header.get_attribute("class") or ""
    if "open" not in l1_class:
        await l1_header.click()
    if not l2_title:
        return

    l1_submenu = l1_header.locator("xpath=following-sibling::*[1]")
    l2_header = l1_submenu.locator(".submenu-item", has_text=l2_title).first
    await l2_header.wait_for(state="visible")
    if animate:
        await move_cursor_to_locator(page, l2_header)
        await page.evaluate("window.clickCursor()")

    l2_class = await l2_header.get_attribute("class") or ""
    if "has-children" in l2_class:
        if "open" not in l2_class:
            await l2_header.click()
        if not l3_title:
            return
        l2_submenu = l2_header.locator("xpath=following-sibling::*[1]")
        l3_item = l2_submenu.locator(".sub-submenu-item", has_text=l3_title).first
        if animate:
            await move_cursor_to_locator(page, l3_item)
            await page.evaluate("window.clickCursor()")
        await l3_item.click()
    else:
        await l2_header.click()


# --- CAPTURE ---
async def capture(durations):
    print(f"🎥 Phase Capture Vidéo (Playwright) — cible : {BASE_URL}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=str(VIDEO_DIR),
            viewport={'width': 1440, 'height': 900},
            record_video_size={'width': 1440, 'height': 900}
        )
        page = await context.new_page()
        await install_cursor(page)

        start_capture_time = time.time()

        def get_v_time():
            return time.time() - start_capture_time

        class SyncNarrator:
            """Gère la synchronisation entre les actions de capture et la narration audio."""

            def __init__(self, durations, time_func):
                self.durations = durations
                self.get_v_time = time_func
                self.current_id = None
                self.start_v_time = 0
                self.timestamps = {}

            async def start(self, segment_id):
                if self.current_id:
                    raise RuntimeError(
                        f"❌ ERREUR SYNCHRO : Impossible de démarrer '{segment_id}' car "
                        f"'{self.current_id}' est encore en cours. Appelez .end() d'abord."
                    )
                if segment_id not in self.durations:
                    print(f"⚠️  Attention : ID audio '{segment_id}' inconnu.")
                    return
                self.current_id = segment_id
                self.start_v_time = self.get_v_time()
                self.timestamps[segment_id] = self.start_v_time
                print(f"🎙️ [Sync Start] {segment_id} à {self.start_v_time:.1f}s")

            async def end(self, padding=0.5):
                if not self.current_id:
                    return
                duration = self.durations.get(self.current_id, 5.0)
                target_end = self.start_v_time + duration + padding
                now = self.get_v_time()
                if now < target_end:
                    wait_time = target_end - now
                    print(f"⏳ [Sync Wait] Pause de {wait_time:.1f}s pour finir '{self.current_id}'...")
                    while self.get_v_time() < target_end:
                        await asyncio.sleep(0.1)
                else:
                    print(f"✅ [Sync OK] '{self.current_id}' terminé avant la fin de l'action.")
                self.current_id = None

        narrator = SyncNarrator(durations, get_v_time)
        page.on("dialog", lambda dialog: print(f"💬 Dialogue : {dialog.message}") or asyncio.create_task(dialog.accept()))

        start_capture_time = time.time()

        try:
            print("🎬 Navigation vers l'écran de connexion Klepsydrix...")
            await page.goto(f"{BASE_URL}/login?db={DEMO_DB}", wait_until="load", timeout=30000)
            try:
                await page.wait_for_selector("text=Connexion", timeout=15000)
            except Exception:
                pass

            # --- 01. Intro ---
            # Ce segment est recouvert par la page de garde au montage (voir assemble()) :
            # ce qui se passe ici à l'écran n'apparaît jamais dans la vidéo finale.
            await narrator.start("01_intro")
            await asyncio.sleep(1)
            await narrator.end(padding=1.5)

            # --- 02. Connexion (compte de démonstration) ---
            await narrator.start("02_login")
            print("🎬 Connexion à Klepsydrix")
            try:
                card = page.locator(".login-card")
                if await card.count() > 0:
                    await move_cursor_to_locator(page, card)
                await asyncio.sleep(0.8)

                # Authentification réelle (API), mêmes conventions que
                # frontend/scripts/doc-screenshots/lib.mjs::loginAsDemo — plus fiable qu'une
                # saisie simulée dans le formulaire pour un script non-interactif.
                resp = await page.request.post(
                    f"{BASE_URL}/api/auth/login/local",
                    headers={"X-Klepsydrix-Database": DEMO_DB},
                    data={"identifier": DEMO_IDENTIFIER, "password": DEMO_PASSWORD},
                )
                if not resp.ok:
                    print(f"  ⚠️  Échec de connexion démo : {resp.status} {await resp.text()}")
                await context.add_cookies([{"name": "klepsydrix_db", "value": DEMO_DB, "url": BASE_URL}])

                await page.goto(BASE_URL, wait_until="load", timeout=30000)
                await page.wait_for_selector(".sidebar", timeout=15000)
                print("  ✅ Connecté, arrivée sur l'écran principal")
            except Exception as e:
                print(f"  ⚠️  Connexion : {e}")
            await narrator.end(padding=1.0)

            # --- 03. Grille de l'emploi du temps (écran d'accueil) ---
            await narrator.start("03_timetable_grid")
            print("🎬 Grille de l'emploi du temps (écran d'accueil)")
            try:
                await page.wait_for_selector("text=Cours à planifier", timeout=20000)
                print("  ✅ Grille et panneau 'Cours à planifier' visibles")
            except Exception as e:
                print(f"  ⚠️  Panneau 'Cours à planifier' non détecté : {e}")
            await asyncio.sleep(2)
            await narrator.end(padding=1.0)

            # --- 04. Classes : liste des divisions ---
            await narrator.start("04_divisions")
            print("🎬 Classes — Liste")
            try:
                await open_tree_path(page, ["Emploi du temps", "Classes", "Liste"])
                print("  ✅ Liste des classes affichée")
                await asyncio.sleep(1.8)
            except Exception as e:
                print(f"  ⚠️  Classes > Liste : {e}")
            await narrator.end(padding=1.0)

            # --- 05. Classes : vœux et contraintes ---
            await narrator.start("05_preferences")
            print("🎬 Classes — Vœux et contraintes")
            try:
                await open_tree_path(page, ["Emploi du temps", "Classes", "Vœux et contraintes"])
                await asyncio.sleep(0.8)

                # Sélectionne une classe concrète (6A, comme dans le jeu de démo) pour montrer
                # un vrai panneau de contraintes plutôt que l'état vide "Sélectionnez un élément".
                row_6a = page.get_by_text("6A", exact=True).first
                if await row_6a.count() > 0:
                    await move_cursor_to_locator(page, row_6a)
                    await page.evaluate("window.clickCursor()")
                    await row_6a.click()
                    print("  ✅ Classe 6A sélectionnée, préférences visibles")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Vœux et contraintes : {e}")
            await narrator.end(padding=1.0)

            # --- 06. Enseignants puis Cours ---
            await narrator.start("06_teachers_courses")
            print("🎬 Enseignants — Liste, puis Cours — Liste")
            try:
                await open_tree_path(page, ["Emploi du temps", "Enseignants", "Liste"])
                print("  ✅ Liste des enseignants affichée")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Enseignants > Liste : {e}")
            try:
                await open_tree_path(page, ["Emploi du temps", "Cours", "Liste"])
                print("  ✅ Liste des cours affichée")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  ⚠️  Cours > Liste : {e}")
            await narrator.end(padding=1.0)

            # --- 07. Pré-rentrée : synthèse TRMD ---
            await narrator.start("07_trmd")
            print("🎬 Pré-rentrée — Synthèse TRMD")
            try:
                await open_tree_path(page, ["Pré-rentrée", "TRMD"])
                print("  ✅ Synthèse TRMD affichée")
                await asyncio.sleep(2.2)
            except Exception as e:
                print(f"  ⚠️  TRMD : {e}")
            await narrator.end(padding=1.0)

            # --- 08. Comptes & droits, puis Outro ---
            await narrator.start("08_accounts_outro")
            print("🎬 Paramètres — Comptes & droits — Utilisateurs")
            try:
                await open_tree_path(page, ["Paramètres", "Comptes & droits", "Utilisateurs"])
                print("  ✅ Liste des utilisateurs affichée")
                await asyncio.sleep(1.8)
            except Exception as e:
                print(f"  ⚠️  Comptes & droits : {e}")
            await narrator.end(padding=1.5)

        except Exception as e:
            print(f"  ❌ Erreur critique pendant la capture : {e}")

        await context.close()
        video_path = await page.video.path()
        return video_path, narrator.timestamps


def create_logo_image(size=200):
    """Crée le logo Klepsydrix (sablier blanc sur fond arrondi accent), fidèle à
    frontend/src/components/BaseLogo.vue."""
    img = Image.new('RGBA', (size, size), color=(0, 0, 0, 0))  # Transparent
    draw = ImageDraw.Draw(img)

    # Fond accent avec coins arrondis (rayon = 20% de la taille)
    radius = int(size * 0.2)
    accent = APP_SETTINGS["accent_color"]
    draw.rounded_rectangle(
        [(0, 0), (size, size)],
        radius=radius,
        fill=(accent[0], accent[1], accent[2], 255)
    )

    # Sablier blanc : barre haute, deux triangles se rejoignant au centre, barre basse
    # (approximation du path SVG de BaseLogo.vue : "M5 3h14M5 21h14M7 3v3a5 5..." sur un
    # viewBox 24x24).
    scale = size / 24.0
    x1, x2 = 6 * scale, 18 * scale
    y_top, y_bottom = 5 * scale, 19 * scale
    cx, cy = size / 2, size / 2
    bar_h = 1.6 * scale

    draw.rounded_rectangle([(x1, y_top - bar_h / 2), (x2, y_top + bar_h / 2)], radius=bar_h / 2, fill=(255, 255, 255, 255))
    draw.rounded_rectangle([(x1, y_bottom - bar_h / 2), (x2, y_bottom + bar_h / 2)], radius=bar_h / 2, fill=(255, 255, 255, 255))
    draw.polygon([(x1, y_top), (x2, y_top), (cx, cy)], fill=(255, 255, 255, 255))
    draw.polygon([(x1, y_bottom), (x2, y_bottom), (cx, cy)], fill=(255, 255, 255, 255))

    return img


def create_title_card(duration):
    """Génère la page de garde complète avec PIL + MoviePy."""
    print(f"🎨 Création de la page de garde ({duration:.1f}s)...")

    # Créer une image PIL complète (1920x1080)
    title_img = Image.new('RGB', (1920, 1080), color=APP_SETTINGS["bg_color"])
    draw = ImageDraw.Draw(title_img)

    # Charger les polices (utiliser DejaVuSans-Bold qui ressemble à Inter)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
    except:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 140)
        except:
            title_font = ImageFont.load_default()

    try:
        subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
    except:
        subtitle_font = ImageFont.load_default()

    try:
        footer_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", 34)
    except:
        footer_font = ImageFont.load_default()

    # 1. Logo (créé avec PIL, puis inséré comme image)
    logo_img = create_logo_image(size=220)
    title_img.paste(logo_img, (250, 280), logo_img)

    # 2. Titre principal "Klepsydrix"
    title_text = APP_SETTINGS["title"]
    title_x = 550
    title_y = 300
    draw.text((title_x, title_y), title_text, fill=(24, 32, 43), font=title_font)

    # 3. Sous-titre (multi-ligne)
    subtitle_text = APP_SETTINGS["subtitle"]
    subtitle_lines = subtitle_text.split('\n')
    line_height = 50
    subtitle_y = 550
    for line in subtitle_lines:
        line_bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        line_width = line_bbox[2] - line_bbox[0]
        line_x = (1920 - line_width) // 2
        draw.text((line_x, subtitle_y), line, fill=(80, 80, 80), font=subtitle_font)
        subtitle_y += line_height

    # 4. Barre accent (couleur de la marque)
    bar_width = 1000
    bar_x = (1920 - bar_width) // 2
    bar_y = 780
    bar_height = 8
    draw.rectangle(
        [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
        fill=APP_SETTINGS["accent_color"]
    )

    # 5. Footer
    footer_text = APP_SETTINGS["footer_tagline"]
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0]
    footer_x = (1920 - footer_width) // 2
    footer_y = 850
    draw.text((footer_x, footer_y), footer_text, fill=(120, 120, 120), font=footer_font)

    # Sauvegarder l'image
    title_card_path = AUDIO_DIR / "title_card.png"
    title_img.save(title_card_path)
    print(f"  ✅ Page de garde générée avec PIL")

    # Créer le clip vidéo à partir de l'image
    return mp.ImageClip(str(title_card_path)).with_duration(duration)


# --- MONTAGE ---
def assemble(video_path, durations, audio_paths, timestamps):
    print("🎬 Phase Montage Final...")
    if not os.path.exists(video_path):
        print("  ❌ Fichier vidéo source introuvable.")
        return

    full_video = mp.VideoFileClip(video_path)

    intro_audio_dur = durations.get("01_intro", 5.0)
    intro_total_dur = intro_audio_dur + 1.5
    intro_animation = create_title_card(intro_total_dur)

    # Pas de "saut temporel" pour cette démo : on concatène simplement la page de garde
    # et la capture complète.
    rest_of_video = full_video.subclipped(intro_total_dur, full_video.duration)
    video = mp.concatenate_videoclips([intro_animation, rest_of_video])

    # --- AUDIO ---
    audio_clips = []
    last_audio_end = 0
    overlaps_detected = []

    for sid, t_start in timestamps.items():
        p = audio_paths.get(sid)
        if p and p.exists():
            if t_start < last_audio_end:
                drift = last_audio_end - t_start
                overlaps_detected.append(f"{sid} (décalé de {drift:.2f}s)")
                actual_start = last_audio_end
            else:
                actual_start = t_start

            print(f"  🔊 Calage {sid} à {actual_start:.1f}s")
            a_clip = mp.AudioFileClip(str(p)).with_start(actual_start)
            audio_clips.append(a_clip)
            last_audio_end = actual_start + a_clip.duration + 0.8

    if overlaps_detected:
        print("\n" + "!" * 60)
        print("⚠️  ALERTE SYNCHRO : Des chevauchements audio ont été évités !")
        for msg in overlaps_detected:
            print(f"   - {msg}")
        print("💡 Conseil : Augmentez les temps d'attente (asyncio.sleep) dans capture().")
        print("!" * 60 + "\n")

    if audio_clips:
        video_with_audio = video.with_audio(mp.CompositeAudioClip(audio_clips))
        if last_audio_end > video.duration:
            print(f"⚠️  ATTENTION : L'audio dépasse la vidéo de {last_audio_end - video.duration:.1f}s. Ajout d'un freeze frame.")
            last_frame = video.get_frame(video.duration - 0.05)
            freeze_duration = last_audio_end - video.duration + 1.0
            freeze_clip = mp.ImageClip(last_frame).with_duration(freeze_duration).with_start(video.duration)
            video = mp.CompositeVideoClip([video_with_audio, freeze_clip])
        else:
            video = video_with_audio

    out_name = f"DEMO_KLEPSYDRIX_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    out = BASE_DIR / out_name
    print(f"💾 Génération de {out}...")
    video.write_videofile(str(out), codec="libx264", audio_codec="aac", fps=24)
    print(f"✨ TERMINÉ ! Fichier : {out}")


async def main():
    script_start_time = time.time()
    print("⏱️  Démarrage du script...")

    assemble_only = "--assemble-only" in sys.argv
    meta_path = BASE_DIR / "last_meta.json"

    if not assemble_only:
        for svc in APP_SETTINGS["services"]:
            if not wait_for_service(svc):
                return

    durations, audio_paths = generate_audio()

    if assemble_only:
        if not meta_path.exists():
            print("  ❌ Aucun fichier 'last_meta.json' trouvé. Lancez une capture complète d'abord.")
            return

        print("⚡ Mode Montage Seul activé. Réutilisation de la dernière capture...")
        with open(meta_path, "r") as f:
            meta = json.load(f)
            t_marks = meta["timestamps"]
            v_path = meta.get("video_path")

        if not v_path or not os.path.exists(v_path):
            webms = list(VIDEO_DIR.glob("*.webm"))
            if not webms:
                print("  ❌ Aucune vidéo .webm trouvée dans temp_video/")
                return
            v_path = str(max(webms, key=os.path.getmtime))
            print(f"  🎬 Vidéo détectée : {v_path}")

        assemble(v_path, durations, audio_paths, t_marks)
    else:
        try:
            v_path, t_marks = await capture(durations)
            if v_path:
                with open(meta_path, "w") as f:
                    json.dump({
                        "video_path": v_path,
                        "timestamps": t_marks
                    }, f, indent=2)

                assemble(v_path, durations, audio_paths, t_marks)
        except Exception as e:
            print(f"❌ Échec global : {e}")
            import traceback
            traceback.print_exc()

    # Afficher le temps d'exécution
    elapsed_time = time.time() - script_start_time
    minutes, seconds = divmod(elapsed_time, 60)
    print("\n" + "="*60)
    print(f"✨ Script terminé en {int(minutes)}m {seconds:.1f}s ({elapsed_time:.1f}s total)")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
