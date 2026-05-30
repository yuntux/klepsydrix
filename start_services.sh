#!/bin/bash

# Configuration des répertoires et ports
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$BASE_DIR/backend"
FRONTEND_DIR="$BASE_DIR/frontend"

BACKEND_PORT=8000
FRONTEND_PORT=3000

BACKEND_LOG="$BASE_DIR/backend.log"
FRONTEND_LOG="$BASE_DIR/frontend.log"

show_help() {
    echo "Usage: ./start_services.sh [start|stop|status|logs|restart]"
    echo "  start   : Lance le backend FastAPI et le frontend Vite en tâche de fond"
    echo "  stop    : Arrête les services en cours d'exécution sur les ports $BACKEND_PORT et $FRONTEND_PORT"
    echo "  status  : Vérifie si les services sont en cours d'exécution"
    echo "  logs    : Affiche les derniers logs des services"
    echo "  restart : Redémarre tous les services"
}

check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null; then
        return 0 # Port occupé
    else
        return 1 # Port libre
    fi
}

get_pid_on_port() {
    local port=$1
    lsof -Pi :$port -sTCP:LISTEN -t
}

start_services() {
    echo "=========================================================="
    echo " Démarrage des services Klepsydrix..."
    echo "=========================================================="

    # 1. Vérification et démarrage du backend
    if check_port $BACKEND_PORT; then
        local pid=$(get_pid_on_port $BACKEND_PORT)
        echo "⚠️  Le backend est déjà en cours d'exécution sur le port $BACKEND_PORT (PID: $pid)"
    else
        echo "🚀 Démarrage du backend (FastAPI)..."
        if [ -d "$BACKEND_DIR/.venv" ]; then
            source "$BACKEND_DIR/.venv/bin/activate"
        else
            echo "❌ Erreur: Environnement virtuel introuvable dans $BACKEND_DIR/.venv"
            exit 1
        fi

        PYTHONPATH="$BASE_DIR" uvicorn backend.app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload --reload-dir "$BACKEND_DIR/app" > "$BACKEND_LOG" 2>&1 &
        local backend_pid=$!
        deactivate

        sleep 2
        if ps -p $backend_pid > /dev/null; then
            echo "✅ Backend démarré avec succès (PID: $backend_pid)"
        else
            echo "❌ Échec du démarrage du backend. Consultez le fichier: backend.log"
        fi
    fi

    # 2. Vérification et démarrage du frontend
    if check_port $FRONTEND_PORT; then
        local pid=$(get_pid_on_port $FRONTEND_PORT)
        echo "⚠️  Le frontend est déjà en cours d'exécution sur le port $FRONTEND_PORT (PID: $pid)"
    else
        echo "🚀 Démarrage du frontend (Vite)..."
        cd "$FRONTEND_DIR" || exit 1
        npm run dev -- --host 0.0.0.0 --port $FRONTEND_PORT > "$FRONTEND_LOG" 2>&1 &
        local frontend_pid=$!
        cd "$BASE_DIR" || exit 1

        sleep 2
        if ps -p $frontend_pid > /dev/null; then
            echo "✅ Frontend démarré avec succès (PID: $frontend_pid)"
        else
            echo "❌ Échec du démarrage du frontend. Consultez le fichier: frontend.log"
        fi
    fi

    echo "----------------------------------------------------------"
    echo " Les services sont configurés. Vous pouvez y accéder :"
    echo "  - Frontend : http://localhost:$FRONTEND_PORT"
    echo "  - Backend (Swagger UI) : http://localhost:$BACKEND_PORT/api/docs"
    echo "  - Backend (ReDoc)      : http://localhost:$BACKEND_PORT/api/redoc"
    echo "=========================================================="
}

stop_services() {
    echo "=========================================================="
    echo " Arrêt des services Klepsydrix..."
    echo "=========================================================="

    local stopped=false

    if check_port $BACKEND_PORT; then
        local pid=$(get_pid_on_port $BACKEND_PORT)
        echo "🛑 Arrêt du backend (PID: $pid)..."
        kill $pid 2>/dev/null
        sleep 1
        # Force kill si toujours vivant
        if check_port $BACKEND_PORT; then
            kill -9 $pid 2>/dev/null
        fi
        echo "✅ Backend arrêté."
        stopped=true
    else
        echo "ℹ️  Le backend n'était pas en cours d'exécution."
    fi

    if check_port $FRONTEND_PORT; then
        local pid=$(get_pid_on_port $FRONTEND_PORT)
        echo "🛑 Arrêt du frontend (PID: $pid)..."
        kill $pid 2>/dev/null
        sleep 1
        # Force kill si toujours vivant
        if check_port $FRONTEND_PORT; then
            kill -9 $pid 2>/dev/null
        fi
        echo "✅ Frontend arrêté."
        stopped=true
    else
        echo "ℹ️  Le frontend n'était pas en cours d'exécution."
    fi

    echo "=========================================================="
}

status_services() {
    echo "=========================================================="
    echo " État des services Klepsydrix :"
    echo "----------------------------------------------------------"

    if check_port $BACKEND_PORT; then
        local pid=$(get_pid_on_port $BACKEND_PORT)
        echo "Backend  [FastAPI] : EN COURS D'EXÉCUTION (Port: $BACKEND_PORT, PID: $pid)"
    else
        echo "Backend  [FastAPI] : ARRÊTÉ"
    fi

    if check_port $FRONTEND_PORT; then
        local pid=$(get_pid_on_port $FRONTEND_PORT)
        echo "Frontend [Vite]    : EN COURS D'EXÉCUTION (Port: $FRONTEND_PORT, PID: $pid)"
    else
        echo "Frontend [Vite]    : ARRÊTÉ"
    fi
    echo "=========================================================="
}

show_logs() {
    echo "=== 10 DERNIÈRES LIGNES DES LOGS BACKEND ($BACKEND_LOG) ==="
    if [ -f "$BACKEND_LOG" ]; then
        tail -n 10 "$BACKEND_LOG"
    else
        echo "Aucun fichier log pour le backend."
    fi

    echo ""
    echo "=== 10 DERNIÈRES LIGNES DES LOGS FRONTEND ($FRONTEND_LOG) ==="
    if [ -f "$FRONTEND_LOG" ]; then
        tail -n 10 "$FRONTEND_LOG"
    else
        echo "Aucun fichier log pour le frontend."
    fi
}

# Analyse de l'argument principal
ACTION=${1:-"start"}

case "$ACTION" in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    status)
        status_services
        ;;
    logs)
        show_logs
        ;;
    restart)
        stop_services
        sleep 1
        start_services
        ;;
    *)
        show_help
        ;;
esac
