// Tests unitaires pour dbSession.ts (voir architecture.md, lot 6) — petit module pur (lecture/
// écriture d'un seul cookie), mais dont apiFetch() (services/api.ts) dépend directement : une
// régression ici casserait silencieusement tout le mécanisme multi-base.
import { beforeEach, describe, expect, it } from 'vitest';
import { clearSelectedDatabase, getSelectedDatabase, setSelectedDatabase } from './dbSession';

function clearAllCookies() {
  document.cookie.split(';').forEach((c) => {
    const name = c.split('=')[0].trim();
    if (name) document.cookie = `${name}=; path=/; Max-Age=0`;
  });
}

describe('dbSession', () => {
  beforeEach(() => {
    clearAllCookies();
  });

  it('getSelectedDatabase() retourne null sans cookie', () => {
    expect(getSelectedDatabase()).toBeNull();
  });

  it('setSelectedDatabase() pose le cookie, relu ensuite par getSelectedDatabase()', () => {
    setSelectedDatabase('timetable');
    expect(getSelectedDatabase()).toBe('timetable');
  });

  it('setSelectedDatabase() encode/décode correctement une valeur avec caractères spéciaux', () => {
    setSelectedDatabase('collège & fils');
    expect(getSelectedDatabase()).toBe('collège & fils');
  });

  it('clearSelectedDatabase() efface le cookie', () => {
    setSelectedDatabase('timetable');
    clearSelectedDatabase();
    expect(getSelectedDatabase()).toBeNull();
  });

  it("ne confond pas un cookie klepsydrix_db avec un autre cookie au nom préfixé similaire", () => {
    document.cookie = 'other_klepsydrix_db=intrus; path=/';
    expect(getSelectedDatabase()).toBeNull();
  });
});
