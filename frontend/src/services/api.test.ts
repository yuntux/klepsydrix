// Tests unitaires pour apiFetch() (voir architecture.md, lot 6 "Tests end-to-end frontend" et
// §16.D "Frontend — cookie, écho d'en-tête, sélecteur de base") : le cœur du mécanisme multi-base/
// jeton d'écriture, entièrement en mémoire (pas de serveur nécessaire, contrairement aux parcours
// Playwright qui couvrent les mêmes flux en conditions réelles).
//
// `apiFetch()` garde son état (jeton d'écriture courant) dans une variable de module — chaque test
// réimporte le module à neuf (`vi.resetModules()` + `import()` dynamique) pour ne jamais hériter de
// l'état d'un test précédent.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

function mockResponse(init: { status?: number; headers?: Record<string, string>; body?: any } = {}) {
  const headers = new Headers(init.headers || {});
  const status = init.status ?? 200;
  return {
    ok: status >= 200 && status < 300,
    status,
    headers,
    clone() { return this; },
    json: async () => init.body ?? {},
  } as Response;
}

async function freshApiFetch() {
  vi.resetModules();
  return (await import('./api')).apiFetch;
}

describe('apiFetch', () => {
  let originalLocation: Location;
  let locationAssignments: string[];

  beforeEach(() => {
    document.cookie = 'klepsydrix_db=; path=/; SameSite=Lax; Max-Age=0';
    document.cookie = 'klepsydrix_session=; path=/; SameSite=Lax; Max-Age=0';
    locationAssignments = [];
    originalLocation = window.location;
    // window.location.href = ... déclenche une vraie navigation en environnement DOM simulé — on
    // remplace l'objet entier par un espion pour observer les assignations sans effet de bord.
    // @ts-expect-error redéfinition volontaire pour le test
    delete window.location;
    window.location = {
      pathname: '/emplois-du-temps',
      search: '',
      reload: vi.fn(),
      set href(value: string) { locationAssignments.push(value); },
      get href() { return locationAssignments.at(-1) ?? ''; },
    } as unknown as Location;
  });

  afterEach(() => {
    window.location = originalLocation;
    vi.unstubAllGlobals();
  });

  it("attache l'en-tête X-Klepsydrix-Database depuis le cookie klepsydrix_db", async () => {
    document.cookie = 'klepsydrix_db=timetable; path=/; SameSite=Lax';
    const fetchMock = vi.fn().mockResolvedValue(mockResponse());
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get('X-Klepsydrix-Database')).toBe('timetable');
  });

  it("n'attache aucun en-tête de base sans cookie klepsydrix_db", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse());
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get('X-Klepsydrix-Database')).toBeNull();
  });

  it('401 NOT_AUTHENTICATED redirige vers /login en portant la page et la base courantes', async () => {
    document.cookie = 'klepsydrix_db=timetable; path=/; SameSite=Lax';
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 401, body: { detail: { code: 'NOT_AUTHENTICATED' } } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    expect(locationAssignments).toHaveLength(1);
    const redirectUrl = new URL(locationAssignments[0], 'http://localhost');
    expect(redirectUrl.pathname).toBe('/login');
    expect(redirectUrl.searchParams.get('next')).toBe('/emplois-du-temps');
    expect(redirectUrl.searchParams.get('db')).toBe('timetable');
  });

  it('403 MASTER_IDENTITY_FORBIDDEN redirige vers /login (mot de passe maître, pas un vrai compte)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, body: { detail: { code: 'MASTER_IDENTITY_FORBIDDEN' } } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    expect(locationAssignments).toHaveLength(1);
    expect(new URL(locationAssignments[0], 'http://localhost').pathname).toBe('/login');
  });

  it("403 sur un autre code d'erreur ne redirige PAS (ex: droit refusé sur une ressource)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 403, body: { detail: 'Droit « write » refusé sur courses.' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/generic/courses/1', { method: 'PATCH' });

    expect(locationAssignments).toHaveLength(0);
  });

  it("401 sur un autre code d'erreur ne redirige PAS (pas une session expirée)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 401, body: { detail: 'Identifiant ou mot de passe incorrect.' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/auth/login/local', { method: 'POST' });

    expect(locationAssignments).toHaveLength(0);
  });

  it('DATABASE_UNKNOWN (404) avec un cookie de base présent redirige vers /select-database', async () => {
    document.cookie = 'klepsydrix_db=base-supprimee; path=/; SameSite=Lax';
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 404, body: { detail: { code: 'DATABASE_UNKNOWN' } } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    expect(locationAssignments).toHaveLength(1);
    expect(new URL(locationAssignments[0], 'http://localhost').pathname).toBe('/select-database');
    // Le cookie de base périmé est effacé, pas seulement ignoré (voir dbSession.ts::clearSelectedDatabase).
    expect(document.cookie).not.toMatch(/klepsydrix_db=base-supprimee/);
  });

  it('un 404 QUELCONQUE (pas un code structuré) ne déclenche PAS la redirection de sélection de base', async () => {
    // Distingue un vrai 404 applicatif (ex: /api/instance/admin/databases/xyz, "Base introuvable.",
    // detail en simple chaîne) du code structuré {code: DATABASE_UNKNOWN} — voir instance_endpoints.py.
    document.cookie = 'klepsydrix_db=timetable; path=/; SameSite=Lax';
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 404, body: { detail: 'Base introuvable.' } }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/instance/admin/databases/xyz');

    expect(locationAssignments).toHaveLength(0);
  });

  it("un écho d'en-tête de base différent du cookie déclenche un rechargement forcé", async () => {
    document.cookie = 'klepsydrix_db=timetable; path=/; SameSite=Lax';
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ status: 200, headers: { 'X-Klepsydrix-Database': 'autre-base' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    expect((window.location.reload as any)).toHaveBeenCalled();
    const mismatchEvent = dispatchSpy.mock.calls.map(c => c[0]).find(e => e.type === 'database:mismatch');
    expect(mismatchEvent).toBeTruthy();
    expect((mismatchEvent as CustomEvent).detail).toEqual({ expected: 'timetable', echoed: 'autre-base' });
  });

  it('un jeton X-Write-Token nouvellement connu (première réponse) ne déclenche PAS write-token:stale', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse({ headers: { 'X-Write-Token': 'jeton-1' } }),
    );
    vi.stubGlobal('fetch', fetchMock);
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus');

    expect(dispatchSpy.mock.calls.map(c => c[0]).some(e => e.type === 'write-token:stale')).toBe(false);
  });

  it('un jeton X-Write-Token qui CHANGE après avoir déjà été connu déclenche write-token:stale', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(mockResponse({ headers: { 'X-Write-Token': 'jeton-1' } }))
      .mockResolvedValueOnce(mockResponse({ status: 409, headers: { 'X-Write-Token': 'jeton-2' } }));
    vi.stubGlobal('fetch', fetchMock);

    const apiFetch = await freshApiFetch();
    await apiFetch('/api/ui/menus'); // connaît jeton-1

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    await apiFetch('/api/timetable/courses/1', { method: 'PUT' }); // reçoit jeton-2, rejeté 409

    const staleEvent = dispatchSpy.mock.calls.map(c => c[0]).find(e => e.type === 'write-token:stale') as CustomEvent;
    expect(staleEvent).toBeTruthy();
    // 409 sur une méthode d'écriture : l'appelant doit distinguer "ma propre écriture vient d'être
    // rejetée" (notification explicite) de "une lecture est simplement périmée" (silencieux) — voir
    // App.vue, écouteur de cet évènement.
    expect(staleEvent.detail).toEqual({ wasWriteAttempt: true });
  });

  it('getWriteToken() reflète le dernier jeton connu', async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse({ headers: { 'X-Write-Token': 'jeton-abc' } }));
    vi.stubGlobal('fetch', fetchMock);

    const apiModule = await (async () => { vi.resetModules(); return import('./api'); })();
    expect(apiModule.getWriteToken()).toBeNull();
    await apiModule.apiFetch('/api/ui/menus');
    expect(apiModule.getWriteToken()).toBe('jeton-abc');
  });
});
