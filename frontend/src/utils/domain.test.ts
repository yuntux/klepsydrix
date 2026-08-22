/**
 * Domaine de filtre façon Odoo (domain.ts) — évaluation d'un arbre ET/OU contre un item déjà
 * aplati, et les conversions arbre <-> notation préfixée qui alimentent le constructeur visuel
 * (GenericListDomainGroupEditor.vue). C'est la seule partie de la refonte du filtrage qui puisse
 * silencieusement montrer/cacher les mauvaises lignes si la logique est fausse — jsdom n'apporte
 * rien ici, tout est pur.
 */
import { describe, it, expect } from 'vitest';
import { evaluateDomain, domainTreeToPrefix, prefixToDomainTree, type DomainNode, type DomainGroupNode } from './domain';

describe('evaluateDomain', () => {
  it('retourne true pour un domaine vide (aucun filtre actif)', () => {
    expect(evaluateDomain({ a: 1 }, [])).toBe(true);
    expect(evaluateDomain({ a: 1 }, null)).toBe(true);
  });

  it('évalue une simple égalité', () => {
    expect(evaluateDomain({ status: 'actif' }, [['status', '=', 'actif']])).toBe(true);
    expect(evaluateDomain({ status: 'inactif' }, [['status', '=', 'actif']])).toBe(false);
  });

  it('combine les termes de haut niveau en ET implicite', () => {
    const domain: DomainNode = [['a', '=', 1], ['b', '=', 2]];
    expect(evaluateDomain({ a: 1, b: 2 }, domain)).toBe(true);
    expect(evaluateDomain({ a: 1, b: 3 }, domain)).toBe(false);
  });

  it('applique le connecteur "|" (OU)', () => {
    const domain: DomainNode = ['|', ['ville', '=', 'Paris'], ['ville', '=', 'Lyon']];
    expect(evaluateDomain({ ville: 'Paris' }, domain)).toBe(true);
    expect(evaluateDomain({ ville: 'Lyon' }, domain)).toBe(true);
    expect(evaluateDomain({ ville: 'Nice' }, domain)).toBe(false);
  });

  it('applique le connecteur "&" explicite imbriqué dans un "|"', () => {
    // (a=1 ET b=2) OU c=3
    const domain: DomainNode = ['|', '&', ['a', '=', 1], ['b', '=', 2], ['c', '=', 3]];
    expect(evaluateDomain({ a: 1, b: 2, c: 0 }, domain)).toBe(true);
    expect(evaluateDomain({ a: 1, b: 0, c: 3 }, domain)).toBe(true);
    expect(evaluateDomain({ a: 1, b: 0, c: 0 }, domain)).toBe(false);
  });

  it('applique le connecteur "!" (NON)', () => {
    const domain: DomainNode = ['!', ['status', '=', 'archive']];
    expect(evaluateDomain({ status: 'actif' }, domain)).toBe(true);
    expect(evaluateDomain({ status: 'archive' }, domain)).toBe(false);
  });

  it('opérateurs de comparaison numérique', () => {
    expect(evaluateDomain({ n: 5 }, [['n', '>', 3]])).toBe(true);
    expect(evaluateDomain({ n: 5 }, [['n', '<', 3]])).toBe(false);
    expect(evaluateDomain({ n: 5 }, [['n', '>=', 5]])).toBe(true);
    expect(evaluateDomain({ n: 5 }, [['n', '<=', 4]])).toBe(false);
  });

  it('opérateurs in / not in', () => {
    expect(evaluateDomain({ grade: 6 }, [['grade', 'in', [6, 5]]])).toBe(true);
    expect(evaluateDomain({ grade: 4 }, [['grade', 'in', [6, 5]]])).toBe(false);
    expect(evaluateDomain({ grade: 4 }, [['grade', 'not in', [6, 5]]])).toBe(true);
  });

  it('like/ilike sont toujours des sous-chaînes (même convention que access_control.py)', () => {
    expect(evaluateDomain({ name: 'Sixième A' }, [['name', 'like', 'ième']])).toBe(true);
    expect(evaluateDomain({ name: 'Sixième A' }, [['name', 'ilike', 'SIXIÈME']])).toBe(true);
    expect(evaluateDomain({ name: 'Sixième A' }, [['name', 'like', 'SIXIÈME']])).toBe(false);
  });

  it('ne lève jamais sur un domaine structurellement invalide — repli sur true', () => {
    const consoleWarn = console.warn;
    console.warn = () => {};
    expect(evaluateDomain({ a: 1 }, ['&', ['a', '=', 1]] as any)).toBe(true); // '&' incomplet
    console.warn = consoleWarn;
  });
});

describe('domainTreeToPrefix / prefixToDomainTree — round-trip', () => {
  it('un groupe vide donne un domaine vide', () => {
    expect(domainTreeToPrefix({ connector: '&', children: [] })).toEqual([]);
  });

  it('une seule condition ne produit aucun connecteur superflu', () => {
    const tree: DomainGroupNode = { connector: '&', children: [{ field: 'a', operator: '=', value: 1 }] };
    expect(domainTreeToPrefix(tree)).toEqual([['a', '=', 1]]);
  });

  it('un groupe OU à 2 conditions', () => {
    const tree: DomainGroupNode = {
      connector: '|',
      children: [{ field: 'ville', operator: '=', value: 'Paris' }, { field: 'ville', operator: '=', value: 'Lyon' }],
    };
    const prefix = domainTreeToPrefix(tree);
    expect(prefix).toEqual(['|', ['ville', '=', 'Paris'], ['ville', '=', 'Lyon']]);
    // Round-trip : reparser doit redonner un arbre équivalent (même connecteur, mêmes enfants).
    expect(prefixToDomainTree(prefix)).toEqual(tree);
  });

  it('un groupe ET à 3 conditions s\'aplatit en un seul groupe (pas de sous-groupes inutiles)', () => {
    const tree: DomainGroupNode = {
      connector: '&',
      children: [
        { field: 'a', operator: '=', value: 1 },
        { field: 'b', operator: '=', value: 2 },
        { field: 'c', operator: '=', value: 3 },
      ],
    };
    const prefix = domainTreeToPrefix(tree);
    expect(prefix).toEqual(['&', '&', ['a', '=', 1], ['b', '=', 2], ['c', '=', 3]]);
    const reparsed = prefixToDomainTree(prefix);
    expect(reparsed.connector).toBe('&');
    expect(reparsed.children).toHaveLength(3);
  });

  it('un sous-groupe imbriqué de connecteur différent reste imbriqué', () => {
    const tree: DomainGroupNode = {
      connector: '&',
      children: [
        { field: 'active', operator: '=', value: true },
        { connector: '|', children: [{ field: 'a', operator: '=', value: 1 }, { field: 'b', operator: '=', value: 2 }] },
      ],
    };
    const prefix = domainTreeToPrefix(tree);
    // Round-trip fonctionnellement équivalent : évalué comme active=true ET (a=1 OU b=2).
    expect(evaluateDomain({ active: true, a: 1, b: 0 }, prefix)).toBe(true);
    expect(evaluateDomain({ active: true, a: 0, b: 0 }, prefix)).toBe(false);
    expect(evaluateDomain({ active: false, a: 1, b: 0 }, prefix)).toBe(false);
  });

  it('prefixToDomainTree sur un domaine vide/absent renvoie un groupe ET vide', () => {
    expect(prefixToDomainTree([])).toEqual({ connector: '&', children: [] });
    expect(prefixToDomainTree(undefined)).toEqual({ connector: '&', children: [] });
  });

  it('rejette explicitement "!" (non représentable dans l\'arbre ET/OU de l\'éditeur visuel)', () => {
    expect(() => prefixToDomainTree(['!', ['a', '=', 1]])).toThrow();
  });
});
