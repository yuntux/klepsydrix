/**
 * Nœuds de layout dans une étape de wizard (groupe, séparateur…).
 *
 * Une étape ne déclare qu'UNE liste, alors que GenericForm en attend deux : les champs à plat —
 * c'est là qu'il résout chaque `key` — et l'arbre de disposition. Le wizard dédouble donc la liste
 * de l'étape. Sans cela, un groupe s'affichait vide : ses enfants, jamais remontés dans `fields`,
 * étaient introuvables.
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import GenericWizard from './GenericWizard.vue';

const GROUPE_PERIMETRE = {
  type: 'group',
  string: "Périmètre de l'import",
  children: [
    { key: 'import_school', label: "Importer les données communes de l'établissement", type: 'boolean' },
    { key: 'import_teachers', label: 'Importer les enseignants', type: 'boolean' },
    { key: 'import_services', label: 'Importer les services', type: 'boolean' },
  ],
};

function monter(fields: any[]) {
  setActivePinia(createPinia());
  return mount(GenericWizard, {
    props: {
      recordId: 1,
      resourceKey: 'wizard_sts_imports',
      model: { id: 1, import_school: true, import_teachers: true, import_services: false },
      steps: [{ id: 'perimetre', title: 'Contenu', fields }],
    },
    global: { stubs: { BaseModal: true, ReportPrintMenu: true } },
  });
}

describe('GenericWizard — layout dans une étape', () => {
  it('rend un groupe, son titre et TOUS ses champs', () => {
    const w = monter([GROUPE_PERIMETRE]);
    const groupe = w.find('.form-layout-group');
    expect(groupe.exists()).toBe(true);
    expect(groupe.text()).toContain("Périmètre de l'import");
    expect(groupe.text()).toContain("Importer les données communes de l'établissement");
    expect(groupe.text()).toContain('Importer les enseignants');
    expect(groupe.text()).toContain('Importer les services');
  });

  it('câble les champs du groupe sur le brouillon', () => {
    // Le piège que ce test verrouille : un groupe rendu mais dont les champs sont vides parce que
    // leur `key` n'a pas été retrouvée dans la liste à plat.
    const w = monter([GROUPE_PERIMETRE]);
    const cases = w.findAll('.form-layout-group input[type="checkbox"]');
    expect(cases).toHaveLength(3);
    expect((cases[0].element as HTMLInputElement).checked).toBe(true);
    expect((cases[2].element as HTMLInputElement).checked).toBe(false);
  });

  it('mélange champs libres et groupes dans la même étape', () => {
    const w = monter([
      { key: 'info_html', label: null, type: 'html' },
      GROUPE_PERIMETRE,
    ]);
    expect(w.findAll('.form-layout-group')).toHaveLength(1);
    expect(w.findAll('.form-layout-group input[type="checkbox"]')).toHaveLength(3);
  });

  it('laisse intactes les étapes sans nœud de layout', () => {
    // Aucun arbre transmis dans ce cas : GenericForm reste sur son repli habituel, tous les champs
    // à plat dans l'ordre déclaré.
    const w = monter([{ key: 'import_school', label: 'Importer', type: 'boolean' }]);
    expect(w.find('.form-layout-group').exists()).toBe(false);
    expect(w.findAll('input[type="checkbox"]')).toHaveLength(1);
  });
});
