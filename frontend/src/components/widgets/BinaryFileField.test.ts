/**
 * Ordre et lisibilité des actions du champ binaire générique.
 *
 * Le point vérifié ici n'est pas décoratif : « Parcourir… » est la seule action toujours
 * disponible, et la seule qui ait un sens quand le champ est encore vide. Elle doit donc précéder
 * le nom de fichier, dont le `flex: 1` rejetait jusque-là toutes les actions à l'extrême droite.
 */
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import BinaryFileField from './BinaryFileField.vue';

const FICHIER = { filename: 'rapport.pdf', mime_type: 'application/pdf', data_base64: 'AAAA' };

function monter(props: any = {}) {
  return mount(BinaryFileField, { props: { modelValue: null, ...props } });
}

/** Tags et textes des enfants directs, dans l'ordre du DOM. */
function sequence(wrapper: any) {
  return Array.from(wrapper.find('.binary-field').element.children)
    .filter((e: any) => e.className !== 'binary-field-input')
    .map((e: any) => (e.textContent || '').trim());
}

describe('BinaryFileField — disposition des actions', () => {
  it('place Parcourir avant le nom de fichier', () => {
    expect(sequence(monter())).toEqual(['Parcourir…', 'Aucun fichier']);
  });

  it('garde Télécharger et Effacer à droite du nom, une fois un fichier présent', () => {
    expect(sequence(monter({ modelValue: FICHIER }))).toEqual([
      'Parcourir…', 'rapport.pdf', '📥', '🗑',
    ]);
  });

  it('nomme le bouton en toutes lettres plutôt que par une icône de dossier', () => {
    const w = monter();
    expect(w.text()).toContain('Parcourir…');
    expect(w.text()).not.toContain('📁');
  });

  it('ouvre le sélecteur de fichier au clic', async () => {
    const w = monter();
    const input = w.find('input[type="file"]').element as HTMLInputElement;
    const clic = vi.spyOn(input, 'click');
    await w.find('.btn-binary-browse').trigger('click');
    expect(clic).toHaveBeenCalled();
  });

  it('disparaît quand le champ est en lecture seule', () => {
    const w = monter({ modelValue: FICHIER, disabled: true });
    expect(w.find('.btn-binary-browse').exists()).toBe(false);
    // Télécharger reste : consulter un fichier n'est pas le modifier.
    expect(sequence(w)).toEqual(['rapport.pdf', '📥']);
  });
});
