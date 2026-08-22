/**
 * Widget image d'un champ binaire (ImageField.vue) : capture webcam et fidélité de l'aperçu.
 *
 * Ce qui est vérifié ici tient en deux points, tous deux invisibles à la relecture : le bouton de
 * capture disparaît bien en lecture seule (un champ non modifiable ne doit offrir aucune action qui
 * le modifierait), et l'aperçu adopte le ratio de l'image RÉELLEMENT stockée, pas un format supposé.
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ImageField from './ImageField.vue';
import { ID_PHOTO_RATIO } from './photoCrop';

const IMAGE = { filename: 'photo.jpg', mime_type: 'image/jpeg', data_base64: 'AAAA' };

function monter(props: any = {}) {
  return mount(ImageField, {
    props: { modelValue: null, ...props },
    global: { stubs: { WebcamCaptureModal: true } },
  });
}

describe('ImageField — capture webcam', () => {
  it('propose un bouton de prise de photo', () => {
    expect(monter().find('.btn-webcam').exists()).toBe(true);
  });

  it('retire le bouton quand le champ est en lecture seule', () => {
    const w = monter({ modelValue: IMAGE, disabled: true });
    expect(w.find('.btn-webcam').exists()).toBe(false);
    // Le composant de capture lui-même n'est pas monté non plus : pas de webcam allumable depuis
    // un champ qu'on n'a pas le droit de modifier.
    expect(w.findComponent({ name: 'WebcamCaptureModal' }).exists()).toBe(false);
  });

  it('ouvre la fenêtre de capture au clic', async () => {
    const w = monter();
    await w.find('.btn-webcam').trigger('click');
    expect(w.findComponent({ name: 'WebcamCaptureModal' }).props('modelValue')).toBe(true);
  });

  it('remonte la photo capturée comme valeur du champ', async () => {
    const w = monter();
    w.findComponent({ name: 'WebcamCaptureModal' }).vm.$emit('capture', IMAGE);
    await w.vm.$nextTick();

    expect(w.emitted('update:modelValue')?.[0]).toEqual([IMAGE]);
  });

  it('transmet le format demandé par widgetParams plutôt que le format par défaut', () => {
    const w = monter({ widgetParams: { photoRatio: 1, photoWidth: 512 } });
    const modal = w.findComponent({ name: 'WebcamCaptureModal' });

    expect(modal.props('ratio')).toBe(1);
    expect(modal.props('outputWidth')).toBe(512);
  });

  it('retombe sur le format photo d\'identité sans paramétrage', () => {
    expect(monter().findComponent({ name: 'WebcamCaptureModal' }).props('ratio')).toBe(ID_PHOTO_RATIO);
  });
});

describe('ImageField — fidélité de l\'aperçu', () => {
  it('adopte le ratio réel de l\'image une fois celle-ci chargée', async () => {
    const w = monter({ modelValue: IMAGE });
    const img = w.find('.image-field-preview');

    // jsdom ne décode aucune image : on simule le chargement avec des dimensions connues, ce que
    // fait le navigateur avant de déclencher `load`.
    Object.defineProperty(img.element, 'naturalWidth', { value: 800, configurable: true });
    Object.defineProperty(img.element, 'naturalHeight', { value: 600, configurable: true });
    await img.trigger('load');

    expect(w.find('.image-field-preview').attributes('style')).toContain('aspect-ratio: 1.333');
  });

  it('part du format de capture tant que l\'image n\'est pas chargée', () => {
    // Repli assumé : jamais un carré, qui ferait sauter l'aperçu de forme au premier rendu, puis
    // encore une fois au chargement.
    const w = monter({ modelValue: IMAGE });
    expect(w.find('.image-field-preview').attributes('style')).toContain(`aspect-ratio: ${ID_PHOTO_RATIO}`);
  });

  it('n\'affiche aucun aperçu tant que le champ est vide', () => {
    expect(monter().find('.image-field-preview').exists()).toBe(false);
  });
});
