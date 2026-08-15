// Sélection de la base courante côté navigateur (voir architecture.md, multi-base) — un simple
// cookie, lu/écrit ici, jamais HttpOnly (apiFetch(), services/api.ts, doit pouvoir le lire pour
// poser l'en-tête X-Klepsydrix-Database sur chaque requête).
const COOKIE_NAME = 'klepsydrix_db';

export function getSelectedDatabase(): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`));
  // Une valeur vide (cookie présent mais sans contenu, ex: certains environnements n'expirent pas
  // un Max-Age=0 aussi agressivement qu'un vrai navigateur) n'est jamais un slug de base valide
  // (voir db_registry.py::SLUG_PATTERN, backend) — traitée comme "aucune base sélectionnée".
  if (!match || !match[1]) return null;
  return decodeURIComponent(match[1]);
}

export function setSelectedDatabase(slug: string): void {
  document.cookie = `${COOKIE_NAME}=${encodeURIComponent(slug)}; path=/; SameSite=Lax`;
}

export function clearSelectedDatabase(): void {
  document.cookie = `${COOKIE_NAME}=; path=/; SameSite=Lax; Max-Age=0`;
}
