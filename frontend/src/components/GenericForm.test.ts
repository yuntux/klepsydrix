/**
 * Libellé nul dans la fiche générique : aucun label affiché, et le widget récupère la largeur.
 *
 * Trois états distincts pour un libellé, et c'est tout l'objet de ces tests — `null` n'est ni
 * `undefined` ni `""` :
 *   - absent   : on hérite du libellé du modèle ;
 *   - `""`     : libellé vide, mais bien présent — la colonne reste réservée ;
 *   - `null`   : aucun libellé, la colonne du label disparaît au profit du widget.
 *
 * La règle ne vaut QUE pour la fiche : les colonnes de liste continuent de retomber sur le nom du
 * champ (voir App.vue::buildColumnsConfig), une colonne sans en-tête n'ayant pas de sens.
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import GenericForm from './GenericForm.vue';

function monter(fields: any[], formConfig?: any, inline = true) {
  setActivePinia(createPinia());
  return mount(GenericForm, {
    props: {
      title: 'Fiche',
      fields,
      modelValue: { id: 1, nom: 'Test', note: 'Texte libre' },
      inline,
      formConfig,
    },
    global: { stubs: { BaseModal: true, GenericWizard: true, ReportPrintMenu: true } },
  });
}

const CHAMP_NOM = { key: 'nom', label: 'Nom', type: 'text' };

/** Style inline effectivement posé sur le widget d'un champ (le voisin direct de son label). */
function colonnesDuWidget(wrapper: any, index = 0) {
  const conteneur = wrapper.find('.fields-layout-container');
  const enfants = Array.from(conteneur.element.children) as HTMLElement[];
  const widgets = enfants.filter(e => !e.classList.contains('form-label'));
  return widgets[index]?.style.gridColumn || '';
}

describe('GenericForm — libellé nul', () => {
  it('affiche le label quand le champ en déclare un', () => {
    const w = monter([CHAMP_NOM]);
    expect(w.findAll('label.form-label')).toHaveLength(1);
    expect(w.find('label.form-label').text()).toContain('Nom');
  });

  it('masque le label et élargit le widget quand le modèle déclare label: None', () => {
    // labelHidden vient de info={"label": None} côté backend (voir generic.py::_apply_label).
    const w = monter([{ ...CHAMP_NOM, labelHidden: true }]);
    expect(w.findAll('label.form-label')).toHaveLength(0);
    // En mode inline la grille compte deux colonnes : le widget les prend toutes les deux.
    expect(colonnesDuWidget(w)).toBe('span 2');
  });

  it('masque le label quand ui.json surcharge overrideLabel à null', () => {
    const w = monter([CHAMP_NOM], { fields: [{ key: 'nom', overrideLabel: null }] });
    expect(w.findAll('label.form-label')).toHaveLength(0);
    expect(colonnesDuWidget(w)).toBe('span 2');
  });

  it('une surcharge à null gagne contre le libellé du modèle', () => {
    // Le piège que ce test verrouille : `elem.overrideLabel || original.label` retombait sur le
    // libellé du modèle, `null` étant falsy — la surcharge était donc ignorée.
    const w = monter([{ ...CHAMP_NOM, label: 'Libellé du modèle' }], {
      fields: [{ key: 'nom', overrideLabel: null }],
    });
    expect(w.text()).not.toContain('Libellé du modèle');
  });

  it('une chaîne vide reste un libellé : la colonne est réservée, pas supprimée', () => {
    const w = monter([{ ...CHAMP_NOM, label: '' }]);
    expect(w.findAll('label.form-label')).toHaveLength(1);
    expect(colonnesDuWidget(w)).toBe('auto');
  });

  it('un champ pleine largeur sans libellé occupe la ligne entière', () => {
    // Hors mode inline, la grille compte quatre colonnes (deux paires label/widget) : un champ
    // pleine largeur en prenait trois, la quatrième étant sa colonne de label — sans label, il
    // les prend toutes.
    const w = monter([{ ...CHAMP_NOM, fullWidth: true, labelHidden: true }], undefined, false);
    expect(w.findAll('label.form-label')).toHaveLength(0);
    expect(colonnesDuWidget(w)).toBe('span 4');
  });

  it('un champ pleine largeur AVEC libellé garde ses trois colonnes', () => {
    const w = monter([{ ...CHAMP_NOM, fullWidth: true }], undefined, false);
    expect(colonnesDuWidget(w)).toBe('span 3');
  });

  it('ne masque que le label visé, les autres champs gardent le leur', () => {
    const w = monter([{ ...CHAMP_NOM, labelHidden: true }, { key: 'note', label: 'Note', type: 'text' }]);
    const labels = w.findAll('label.form-label');
    expect(labels).toHaveLength(1);
    expect(labels[0].text()).toContain('Note');
  });
});
