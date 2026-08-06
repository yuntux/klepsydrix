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

export type WidgetContext = 'list' | 'form';

interface WidgetRegistryEntry {
  component: any;
  contexts?: WidgetContext[];
}

const REGISTRY: Record<string, WidgetRegistryEntry> = {
  many2many_ordered_list: { component: Many2ManyOrderedList, contexts: ['form'] },
  course_composition_mapping: { component: CourseCompositionMapping, contexts: ['form'] },
  course_composition_preview: { component: CourseCompositionPreview, contexts: ['form'] },
};

export function getWidgetForContext(name: string | undefined, context: WidgetContext): any {
  if (!name) return null;
  const entry = REGISTRY[name];
  if (!entry) return null;
  const contexts = entry.contexts || ['form'];
  return contexts.includes(context) ? entry.component : null;
}
