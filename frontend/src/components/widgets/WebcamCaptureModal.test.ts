/**
 * Fenêtre de capture par la webcam (WebcamCaptureModal.vue) — ce qui est offert à l'utilisateur
 * selon l'état de la caméra.
 *
 * Le point vérifié ici : quand la webcam est hors de portée (absente, accès refusé, connexion non
 * sécurisée), la fenêtre ne doit proposer QUE de fermer. Un bouton « Prendre la photo » présent
 * mais impuissant invite à cliquer pour rien, et laisse croire à une panne plutôt qu'à une
 * situation attendue dont le message d'erreur explique déjà la sortie.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import WebcamCaptureModal from './WebcamCaptureModal.vue';

/** Ouvre la fenêtre comme le fait le widget : montée fermée, puis ouverte (c'est ce passage qui
 * déclenche l'accès à la caméra). */
async function ouvrir() {
  const w = mount(WebcamCaptureModal, { props: { modelValue: false } });
  await w.setProps({ modelValue: true });
  await new Promise(r => setTimeout(r, 0));   // laisse start() se dérouler
  await w.vm.$nextTick();
  return w;
}

function libelles(w: any) {
  return w.findAllComponents({ name: 'BaseButton' }).map((b: any) => b.text().trim());
}

/**
 * Un vrai `MediaStream` : l'assignation à `video.srcObject` refuse tout autre objet (le DOM
 * vérifie le type), et un simple littéral déclencherait une erreur non rattrapée hors des
 * assertions — un test qui passe en laissant une exception derrière lui n'est pas un test vert.
 * `getTracks` est ajouté à la main, l'implémentation du DOM de test ne le fournissant pas.
 */
function fluxFactice(pistes: any[] = []) {
  const stream = new MediaStream();
  (stream as any).getTracks = () => pistes;
  return stream;
}

describe('WebcamCaptureModal — webcam hors de portée', () => {
  beforeEach(() => {
    // `mediaDevices` retiré : c'est exactement l'état d'un navigateur sur une origine non
    // sécurisée (http), où l'API n'existe tout simplement pas.
    Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
  });

  it('explique que la connexion doit être sécurisée', async () => {
    const w = await ouvrir();
    expect(w.find('.capture-error').text()).toContain('sécurisée');
  });

  it('ne propose que le bouton Annuler', async () => {
    const w = await ouvrir();
    expect(libelles(w)).toEqual(['Annuler']);
  });

  it('ne propose pas non plus la scène vidéo', async () => {
    const w = await ouvrir();
    // v-show : l'élément existe mais reste masqué tant qu'il n'y a rien à filmer.
    expect(w.find('.capture-stage').attributes('style')).toContain('display: none');
  });

  it('signale un refus d\'autorisation autrement qu\'une absence de matériel', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: () => Promise.reject(Object.assign(new Error('nope'), { name: 'NotAllowedError' })) },
      configurable: true,
    });
    const w = await ouvrir();

    expect(w.find('.capture-error').text()).toContain('refusé');
    expect(libelles(w)).toEqual(['Annuler']);
  });
});

describe('WebcamCaptureModal — webcam disponible', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn().mockResolvedValue(fluxFactice()) },
      configurable: true,
    });
  });

  it('propose la capture, sans message d\'erreur', async () => {
    const w = await ouvrir();

    expect(w.find('.capture-error').exists()).toBe(false);
    expect(libelles(w)).toEqual(['Annuler', 'Prendre la photo']);
  });

  it('ferme la fenêtre et coupe le flux au clic sur Annuler', async () => {
    const stop = vi.fn();
    Object.defineProperty(navigator, 'mediaDevices', {
      value: { getUserMedia: vi.fn().mockResolvedValue(fluxFactice([{ stop }])) },
      configurable: true,
    });
    const w = await ouvrir();

    await w.findAllComponents({ name: 'BaseButton' })[0].trigger('click');

    expect(w.emitted('update:modelValue')?.[0]).toEqual([false]);
    // Un flux laissé ouvert garde la webcam allumée, témoin lumineux compris.
    expect(stop).toHaveBeenCalled();
  });
});
