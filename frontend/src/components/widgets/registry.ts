// Registre partagé des widgets de champ "complexes" (déclarés via `widget`/`widgetParams` dans
// ui.json ou dans le dict `info` d'un modèle backend) — utilisé par GenericForm.vue (FormLayoutGrid)
// pour le rendu des champs de formulaire, et par GenericWizard.vue pour le rendu des champs
// d'étape. Un seul point d'enregistrement plutôt que des `if (elem.widget === '...')` codés en dur
// répétés à chaque nouveau widget (voir architecture.md, section wizard générique).
//
// Contrat commun à tout widget de ce registre (voir Many2ManyOrderedList.vue pour un exemple) :
// props { modelValue, field, widgetParams?, disabled?, parentRecord? }, emit('update:modelValue').
//
// `contexts` : dans quelle(s) vue(s) le widget est autorisé à se substituer au rendu par défaut.
// `widget` est déclaré au niveau du MODÈLE (dict `info`), donc valable pour toute vue qui affiche
// ce champ — un widget conçu pour l'espace généreux d'un formulaire (ex: many2many_ordered_list,
// une mini-table éditable complète) n'est pas forcément adapté à une cellule de tableau compacte.
// Défaut : ['form'] uniquement — un widget doit explicitement demander le support liste, plutôt
// que de s'y retrouver par accident (régression réelle rencontrée : "Effectifs par MEF"
// (Division.mef_links, many2many_ordered_list) s'affichait en pleine mini-table dans la colonne
// de la liste "Classes" avant ce correctif).
import Many2ManyOrderedList from './Many2ManyOrderedList.vue';
import CourseCompositionMapping from './CourseCompositionMapping.vue';
import CourseCompositionPreview from './CourseCompositionPreview.vue';
import SystemSettingValueField from './SystemSettingValueField.vue';
import ImageField from './ImageField.vue';
import RelationBrowserField from './RelationBrowserField.vue';
import ListPreviewField from './ListPreviewField.vue';
import TimeslotPickerField from './TimeslotPickerField.vue';
import ClockTimeField from './ClockTimeField.vue';

export type WidgetContext = 'list' | 'form';

interface WidgetRegistryEntry {
  component: any;
  contexts?: WidgetContext[];
}

const REGISTRY: Record<string, WidgetRegistryEntry> = {
  many2many_ordered_list: { component: Many2ManyOrderedList, contexts: ['form'] },
  course_composition_mapping: { component: CourseCompositionMapping, contexts: ['form'] },
  course_composition_preview: { component: CourseCompositionPreview, contexts: ['form'] },
  system_setting_value: { component: SystemSettingValueField, contexts: ['form', 'list'] },
  // 'list' volontairement absent : un champ binaire (avec ou sans widget="image") ne doit jamais
  // afficher son contenu dans une cellule de liste, seulement un badge de présence — voir
  // GenericList.vue, branche type === 'binary'.
  image: { component: ImageField, contexts: ['form'] },
  // Bouton "parcourir/gérer une relation" (one2many ou many2many, jamais many2one) — voir
  // RelationBrowserField.vue. Utilisable en liste ET en formulaire : contrairement à
  // many2many_ordered_list, ce n'est qu'un bouton compact ouvrant une popin, adapté à une cellule
  // de tableau comme à un champ de formulaire.
  relation_browser: { component: RelationBrowserField, contexts: ['list', 'form'] },
  // Aperçu de liste transitoire (lignes déjà en mémoire, jamais fetchées) — voir
  // ListPreviewField.vue. 'form' uniquement : utilisé comme champ d'étape de wizard
  // (GenericWizard.vue délègue déjà à GenericForm, même contrat que tout autre widget de champ).
  list_preview: { component: ListPreviewField, contexts: ['form'] },
  // Voir wizard_grid_settings.py — 'list' pour les colonnes de day_rows/display_rows (cellules
  // éditées inline dans un list_preview), 'form' pour les champs de récréation du wizard lui-même.
  timeslot_picker: { component: TimeslotPickerField, contexts: ['list', 'form'] },
  clock_time: { component: ClockTimeField, contexts: ['list', 'form'] },
};

export function getWidgetForContext(name: string | undefined, context: WidgetContext): any {
  if (!name) return null;
  const entry = REGISTRY[name];
  if (!entry) return null;
  const contexts = entry.contexts || ['form'];
  return contexts.includes(context) ? entry.component : null;
}
