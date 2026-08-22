#!/usr/bin/env bash
# Installation des prérequis et dépendances de Klepsydrix — voir user_doc/superadmin_doc.md §2.
#
# Couvre : Debian/Ubuntu (apt) et macOS (Homebrew). Sous Windows, lancer ce script DANS WSL2
# (voir user_doc/superadmin_doc.md §2.4) — il n'y a pas de chemin natif Windows (start_services.sh
# et ce script sont tous les deux du bash).
#
# Idempotent : peut être relancé sans risque (les paquets déjà installés sont ignorés, le venv et
# instance.yaml ne sont pas recréés s'ils existent déjà).
#
#   ./install.sh
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

# JDK minimum requis par Timefold/JPype (voir dist-info de timefold : "Install JDK 17 or later").
MIN_JAVA_VERSION=17
# Node minimum requis par l'outillage frontend (Vite 5 / vue-tsc / vitest 4).
MIN_NODE_VERSION=20

log()  { echo "==> $*"; }
warn() { echo "⚠️  $*" >&2; }
die()  { echo "❌ $*" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- 1. Dépendances système, selon l'OS -------------------------------------------------------
install_system_deps_debian() {
  log "Debian/Ubuntu détecté — installation des paquets système (sudo requis)."
  sudo apt-get update
  sudo apt-get install -y \
    git \
    python3 python3-venv python3-pip \
    default-jdk \
    nodejs npm \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
}

install_system_deps_macos() {
  command_exists brew || die "Homebrew requis (https://brew.sh) — installez-le puis relancez ce script."
  log "macOS détecté — installation des paquets système via Homebrew."
  brew install git python@3.12 openjdk@17 node pango
  # openjdk@17 n'est pas placé sur le PATH par Homebrew par défaut.
  export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
  warn "Ajoutez à votre shell (~/.zshrc ou ~/.bash_profile) :"
  warn "  export JAVA_HOME=\"$JAVA_HOME\""
  warn "  export PATH=\"\$JAVA_HOME/bin:\$PATH\""
}

OS_NAME="$(uname -s)"
case "$OS_NAME" in
  Linux)
    if command_exists apt-get; then
      install_system_deps_debian
    else
      die "Distribution Linux non-Debian/Ubuntu détectée — installez manuellement : git, python3 (+venv), un JDK $MIN_JAVA_VERSION+, Node.js $MIN_NODE_VERSION+/npm, et les bibliothèques Pango/cairo/harfbuzz de WeasyPrint, puis relancez avec --skip-system pour la suite."
    fi
    ;;
  Darwin)
    install_system_deps_macos
    ;;
  *)
    die "OS '$OS_NAME' non supporté par ce script. Sous Windows, lancez ce script dans WSL2 (voir user_doc/superadmin_doc.md §2.4)."
    ;;
esac

# --- 2. Vérification des versions --------------------------------------------------------------
command_exists java || die "java introuvable après installation — vérifiez JAVA_HOME et le PATH."
JAVA_VERSION="$(java -version 2>&1 | head -1 | grep -oE '"[0-9]+' | tr -d '"' | head -1)"
[ "${JAVA_VERSION:-0}" -ge "$MIN_JAVA_VERSION" ] || warn "Java $JAVA_VERSION détecté, JDK $MIN_JAVA_VERSION+ recommandé par Timefold."

command_exists node || die "node introuvable après installation."
NODE_VERSION="$(node -v | tr -d 'v' | cut -d. -f1)"
[ "$NODE_VERSION" -ge "$MIN_NODE_VERSION" ] || warn "Node.js $NODE_VERSION détecté, $MIN_NODE_VERSION+ recommandé (apt fournit parfois une version ancienne — voir nvm/nodesource si besoin)."

# --- 3. Backend : venv + dépendances Python ----------------------------------------------------
if [ ! -d "$BACKEND_DIR/.venv" ]; then
  log "Création du venv backend ($BACKEND_DIR/.venv)."
  python3 -m venv "$BACKEND_DIR/.venv"
else
  log "venv backend déjà présent, réutilisé."
fi

log "Installation des dépendances Python (backend/requirements.txt)."
"$BACKEND_DIR/.venv/bin/pip" install --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

# --- 4. Frontend : dépendances npm --------------------------------------------------------------
log "Installation des dépendances frontend (npm install)."
(cd "$FRONTEND_DIR" && npm install)

# --- 5. Fichier de configuration instance.yaml --------------------------------------------------
if [ ! -f "$BASE_DIR/instance.yaml" ]; then
  log "Copie d'instance.example.yaml vers instance.yaml (à adapter — voir user_doc/superadmin_doc.md §3)."
  cp "$BASE_DIR/instance.example.yaml" "$BASE_DIR/instance.yaml"
else
  log "instance.yaml déjà présent, laissé tel quel."
fi

cat <<'EOF'

✅ Installation terminée.

Prochaines étapes :
  1. Adapter instance.yaml (voir user_doc/superadmin_doc.md §3) — au minimum, changer secret_key
     avant toute exposition hors localhost.
  2. Créer la première base :
       - démonstration : backend/.venv/bin/python -m backend.app.core.init_demo
       - vide (production) : backend/.venv/bin/python -m backend.app.core.init_db
  3. Démarrer les services :
       ./start_services.sh start
       ./start_services.sh status
EOF
