// Géométrie de la capture photo d'identité (voir WebcamCaptureModal.vue).
//
// Isolée du composant parce que c'est la seule partie réellement susceptible d'être fausse : une
// webcam livre du 4/3 ou du 16/9, la photo attendue est en 35/45 — il faut donc découper, et une
// erreur de calcul ne se voit pas dans le code, seulement sur un visage décentré. Une fonction pure
// se vérifie par des tests (voir photoCrop.test.ts), un `<video>` non.

/**
 * Format d'une photo d'identité française et européenne : 35 mm de large sur 45 mm de haut
 * (norme ISO/IEC 19794-5, reprise par le décret français sur les titres d'identité). Exprimé en
 * largeur/hauteur pour coller à `aspect-ratio` en CSS comme aux dimensions d'un canvas.
 */
export const ID_PHOTO_RATIO = 35 / 45;

/** Largeur de l'image produite, en pixels. 350 × 450 donne 250 dpi à la taille réelle (35×45 mm),
 * au-delà de ce qu'exige une impression de trombinoscope, pour un JPEG de quelques dizaines de Ko. */
export const ID_PHOTO_OUTPUT_WIDTH = 350;

export interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Plus grand rectangle au ratio `targetRatio` (largeur/hauteur) tenant dans une source, centré.
 *
 * Centré, et non aligné en haut : le cadre affiché à l'écran et la zone réellement découpée doivent
 * coïncider exactement, sinon l'utilisateur cadre son visage sur un repère qui ment.
 */
export function computeCropRect(sourceWidth: number, sourceHeight: number, targetRatio: number): CropRect {
  if (sourceWidth <= 0 || sourceHeight <= 0 || targetRatio <= 0) {
    return { x: 0, y: 0, width: 0, height: 0 };
  }
  const sourceRatio = sourceWidth / sourceHeight;
  // Source plus large que la cible : c'est la hauteur qui est limitante, on rogne à gauche/droite.
  const width = sourceRatio > targetRatio ? sourceHeight * targetRatio : sourceWidth;
  const height = sourceRatio > targetRatio ? sourceHeight : sourceWidth / targetRatio;
  return {
    x: (sourceWidth - width) / 2,
    y: (sourceHeight - height) / 2,
    width,
    height,
  };
}

/**
 * Gabarit de visage, en fractions du cadre de découpe (voir l'overlay de WebcamCaptureModal.vue).
 *
 * Valeurs tirées des exigences officielles d'une photo d'identité : le visage (menton au sommet du
 * crâne) doit occuper 32 à 36 mm sur les 45 mm de hauteur, soit ~75 %, avec un espace libre
 * au-dessus de la tête. C'est ce qui fait la différence entre une photo acceptée et une photo
 * refusée au guichet — d'où un gabarit précis plutôt qu'un ovale décoratif.
 */
export const FACE_GUIDE = {
  /** Centre du visage, en fraction de la largeur/hauteur du cadre. */
  centerX: 0.5,
  centerY: 0.47,
  /** Demi-axes de l'ellipse, en fraction de la largeur/hauteur du cadre. */
  radiusX: 0.29,
  radiusY: 0.37,
};
