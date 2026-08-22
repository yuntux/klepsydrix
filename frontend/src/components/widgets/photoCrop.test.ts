/**
 * Géométrie de la capture photo d'identité (photoCrop.ts).
 *
 * C'est la seule partie de la fonctionnalité webcam qui puisse être fausse en silence : le cadre
 * affiché à l'écran et la zone réellement découpée doivent coïncider, sinon l'utilisateur cadre son
 * visage sur un repère qui ment. Un `<video>` ne se teste pas en jsdom ; cette fonction, si.
 */
import { describe, it, expect } from 'vitest';
import { ID_PHOTO_RATIO, computeCropRect } from './photoCrop';

describe('computeCropRect — découpe au format photo d\'identité', () => {
  it('rogne la largeur d\'une webcam 4/3, sans toucher à la hauteur', () => {
    // 1280×960 (4/3) vers 35/45 : la source est bien plus large que la cible.
    const crop = computeCropRect(1280, 960, ID_PHOTO_RATIO);

    expect(crop.height).toBe(960);
    expect(crop.width).toBeCloseTo(960 * ID_PHOTO_RATIO, 5);
    expect(crop.width / crop.height).toBeCloseTo(ID_PHOTO_RATIO, 10);
  });

  it('centre la zone découpée', () => {
    const crop = computeCropRect(1280, 960, ID_PHOTO_RATIO);

    // Autant de marge à gauche qu'à droite : un visage centré à l'écran reste centré sur la photo.
    expect(crop.x).toBeCloseTo((1280 - crop.width) / 2, 5);
    expect(crop.x + crop.width).toBeCloseTo(1280 - crop.x, 5);
    expect(crop.y).toBe(0);
  });

  it('rogne la hauteur quand la source est plus haute que le format visé', () => {
    // Cas d'une webcam en portrait, ou d'un ratio cible plus large que la source.
    const crop = computeCropRect(600, 1600, ID_PHOTO_RATIO);

    expect(crop.width).toBe(600);
    expect(crop.height).toBeCloseTo(600 / ID_PHOTO_RATIO, 5);
    expect(crop.y).toBeCloseTo((1600 - crop.height) / 2, 5);
  });

  it('ne rogne rien quand la source est déjà au bon format', () => {
    const crop = computeCropRect(350, 450, ID_PHOTO_RATIO);

    expect(crop).toEqual({ x: 0, y: 0, width: 350, height: 450 });
  });

  it('reste dans les bornes de la source, quel que soit le ratio demandé', () => {
    for (const ratio of [0.5, ID_PHOTO_RATIO, 1, 16 / 9]) {
      const crop = computeCropRect(1920, 1080, ratio);
      expect(crop.x).toBeGreaterThanOrEqual(0);
      expect(crop.y).toBeGreaterThanOrEqual(0);
      expect(crop.x + crop.width).toBeLessThanOrEqual(1920 + 1e-9);
      expect(crop.y + crop.height).toBeLessThanOrEqual(1080 + 1e-9);
    }
  });

  it('renvoie un rectangle vide plutôt que des NaN sur une source inexploitable', () => {
    // `videoWidth` vaut 0 tant que le flux n'a pas démarré — la capture ne doit pas produire
    // d'image dégénérée, juste ne rien faire.
    expect(computeCropRect(0, 0, ID_PHOTO_RATIO)).toEqual({ x: 0, y: 0, width: 0, height: 0 });
  });

  it('conserve le format 35/45 attendu par les documents d\'identité', () => {
    expect(ID_PHOTO_RATIO).toBeCloseTo(35 / 45, 10);
    // 35 mm de large sur 45 de haut : plus haut que large, jamais l'inverse.
    expect(ID_PHOTO_RATIO).toBeLessThan(1);
  });
});
