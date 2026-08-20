<template>
  <!-- headless : rend uniquement la popin du wizard (BaseModal ci-dessous, hors de ce bloc), sans
       le formulaire/l'en-tête/les boutons — pour un déclenchement direct d'une action de menu (voir
       formConfig.autoOpenActionId) qui ne doit rien afficher tant que le wizard n'est pas ouvert. -->
  <div v-if="!headless" :class="inline ? 'inline-form-container' : 'modal-overlay'">
    <div :class="inline ? 'generic-form-inline' : 'generic-form-modal glass-morphism'">
      <div class="form-header">
        <h3 class="form-title">{{ isMultiEdit ? 'Modification groupée' : title }}</h3>
        <button v-if="!inline" class="btn-close" @click="handleCancel">×</button>
      </div>

      <form @submit.prevent="handleSubmit" class="form-body">
        <div v-if="isMultiEdit" class="multi-edit-banner">
          <span class="multi-edit-banner-icon">✏️</span>
          <div class="multi-edit-banner-content">
            <div class="multi-edit-banner-title">Modification groupée ({{ selectedRecords?.length }} éléments)</div>
            <div class="multi-edit-banner-text">
              Seuls les champs marqués du badge <span class="field-modified-badge-inline">✏️ Modifié</span> seront enregistrés pour tous les éléments sélectionnés. Les autres resteront inchangés.
            </div>
          </div>
        </div>

        <FormLayoutGrid
          :elements="layoutTree"
          :localModel="localModel"
          :isEditableForm="isEditableForm"
          :inline="inline"
          :isMultiEdit="isMultiEdit"
          :initialModelValue="initialModelValue"
        />

        <div class="form-actions">
          <!-- Point d'extension générique, tout à gauche de la ligne d'actions : GenericForm ne
               sait pas ce qui s'y trouve (ex: GenericWizard.vue y place son bouton "Précédent"),
               volontairement pour ne coupler ce composant à aucun besoin spécifique. -->
          <slot name="actions-start"></slot>
          <BaseButton v-if="localModel && localModel.id && !isMultiEdit && isDeletableForm" type="button" variant="danger" class="btn-delete" @click="handleDelete">
            Supprimer
          </BaseButton>

          <!-- Actions dynamiques métier du modèle -->
          <template v-if="localModel && localModel.id && !isMultiEdit">
            <BaseButton
              v-for="action in formActions"
              :key="action.id"
              type="button"
              variant="success"
              @click="handleActionClick(action)"
            >
              {{ action.label || action.name }}
            </BaseButton>
          </template>

          <!-- Impression (voir architecture.md §22) : bouton unique, quelle que soit la portée
               (mono-enregistrement courant, ou tous les enregistrements sélectionnés en édition
               groupée) — resolveIds calcule les ids ciblés selon CE contexte, l'action elle-même
               n'a plus de scope. Absent tant qu'aucun rapport n'est disponible pour ce modèle. -->
          <ReportPrintMenu
            v-if="canPrint"
            :actions="reportActions"
            :resolve-ids="resolvePrintIds"
          />

          <BaseButton type="button" variant="secondary" @click="handleCancel">
            Annuler
          </BaseButton>
          <BaseButton v-if="isEditableForm" type="submit" variant="primary">
            {{ props.submitLabel || 'Enregistrer' }}
          </BaseButton>
        </div>
      </form>
    </div>
  </div>

  <BaseModal v-model="showWizard" :title="activeActionTitle" maxWidth="1600px">
    <component
      v-if="showWizard && activeAction"
      :is="activeAction.component ? componentsMap[activeAction.component] : GenericWizard"
      :recordId="localModel.id"
      :model="localModel"
      :resourceKey="resourceKey"
      :steps="activeAction.steps"
      :cancelRpc="activeAction.cancelRpc"
      @cancel="showWizard = false"
      @success="onWizardSuccess"
    />
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, reactive, watch, computed, defineComponent, h } from 'vue';
import ColorSwatchPicker from './ColorSwatchPicker.vue';
import DurationInput from './DurationInput.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import BaseTooltip from './BaseTooltip.vue';
import BaseToggle from './BaseToggle.vue';
import BaseButton from './BaseButton.vue';
import BaseModal from './BaseModal.vue';
import GenericWizard from './widgets/GenericWizard.vue';
import OwnedRelationField from './widgets/OwnedRelationField.vue';
import BinaryFileField from './widgets/BinaryFileField.vue';
import ReportPrintMenu from './widgets/ReportPrintMenu.vue';
import { getWidgetForContext } from './widgets/registry';
import { useNotificationStore } from '../stores/notifications';
import * as api from '../services/api';

const showWizard = ref(false);
const modelActions = ref<any[]>([]);
const activeAction = ref<any | null>(null);
const activeActionTitle = ref<string>('');

// Table d'exception pour un wizard entièrement bespoke (déclare son propre component au lieu de
// steps) — GenericWizard.vue (générique, piloté par steps) reste le cas par défaut, voir le
// template ci-dessus. Vide aujourd'hui : le seul wizard du projet (décomposition de cours) est
// entièrement passé au mécanisme générique.
const componentsMap: Record<string, any> = {};

// Actions "métier" (wizard, api, bulk_api...) rendues comme boutons individuels — les actions de
// type "report" sont exclues d'ici : elles vivent toutes derrière le bouton unique "Imprimer" (voir
// ReportPrintMenu et reportActions ci-dessous, architecture.md §22.D).
const formActions = computed(() =>
  modelActions.value
    .filter((action: any) => action.type !== 'report')
    .filter((action: any) => evaluateActionCondition(action, localModel.value)),
);

// Rapports disponibles pour l'enregistrement affiché — un seul point d'entrée ("Imprimer"), quelle
// que soit la vue (voir GenericList.vue, même filtre). Les actions "report" n'ont plus de scope :
// c'est resolvePrintIds ci-dessous, propre à CE composant, qui décide des ids ciblés.
const reportActions = computed(() =>
  modelActions.value
    .filter((action: any) => action.type === 'report')
    .filter((action: any) => evaluateActionCondition(action, localModel.value)),
);

const canPrint = computed(() => {
  if (!reportActions.value.length) return false;
  if (isMultiEdit.value) return !!(props.selectedRecords && props.selectedRecords.length);
  return !!(localModel.value && localModel.value.id);
});

// Enregistrement(s) COURANT(s) : celui affiché, ou tous ceux de l'édition groupée — jamais une
// portée plus large, contrairement à l'ancien bouton de portée "list" qui vivait sur GenericList.vue.
function resolvePrintIds(): number[] {
  if (isMultiEdit.value) {
    return (props.selectedRecords || []).map((record: any) => record.id).filter((id: any) => id != null);
  }
  return [localModel.value?.id].filter((id: any) => id != null);
}

function evaluateActionCondition(action: any, model: any) {
  if (!action.condition) return true;
  try {
    const fn = new Function('record', 'model', `return ${action.condition}`);
    return !!fn(model, model);
  } catch (e) {
    return false;
  }
}

function onWizardSuccess(payload: { startsBackgroundJob: boolean }) {
  showWizard.value = false;
  emit('wizard-success', payload);
}

function handleActionClick(action: any) {
  if (action.type === 'wizard') {
    activeAction.value = action;
    activeActionTitle.value = action.label || action.name || 'Assistant';
    showWizard.value = true;
    return;
  }
  // Impression PDF (voir architecture.md §22) : plus traitée ici — voir ReportPrintMenu/
  // reportActions/resolvePrintIds ci-dessus, seul chemin désormais pour les actions "report".
}

interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'color' | 'duration' | 'multiselect' | 'html' | 'json' | 'binary';
  required?: boolean;
  requiredExpr?: string;
  readOnly?: boolean;
  readOnlyExpr?: string;
  invisibleExpr?: string;
  widget?: string;
  widgetParams?: any;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: string;
  fullWidth?: boolean;
  options?: Array<{ value: any; label: string }>;
  help?: string;
  resource?: string;
  // Relation 1-à-N "possédée" (voir generic.py::parentField) — présent seulement sur un champ
  // resource dont les enregistrements ciblés n'existent pas indépendamment du record courant.
  parentField?: string;
  // Reflète Column.nullable côté backend (voir generic.py) — utilisé pour la validation requise.
  nullable?: boolean;
  // Pour un champ type: "duration" dont 0 minute est une valeur valide ("modalité non utilisée") —
  // voir DurationInput.vue::getDurationOptions.
  durationIncludeZero?: boolean;
  // info={"hidden": True} côté backend (voir architecture.md, section E) : un champ calculé qui
  // n'existe que pour nourrir le readOnlyExpr d'un AUTRE champ ne doit jamais devenir son propre
  // champ de formulaire — respecté ici même si l'appelant ne l'a pas déjà filtré en amont.
  hidden?: boolean;
  // Voir LayoutElement.dynamicOptionsFilter plus bas — déclaré ici aussi car un champ de wizard
  // (voir GenericWizard.vue) le porte directement sur le FormField, jamais sur un LayoutElement
  // explicite (les wizards ne passent pas de formConfig.fields).
  dynamicOptionsFilter?: { sourceField: string; filterQueryParam: string; recordIdQueryParam?: string };
}
interface LayoutElement {
  type: 'field' | 'group' | 'separator' | 'newline' | 'notebook' | 'page';
  key?: string;
  string?: string;
  col?: number;
  span?: number;
  children?: LayoutElement[];
  // Identifiant stable d'un noeud 'notebook' (voir notebookActiveIndex plus bas) — permet de
  // piloter son onglet actif depuis l'extérieur (ex: validateRequiredFields le bascule sur
  // l'onglet contenant un champ requis resté vide, y compris s'il n'est pas actif au moment de
  // la soumission).
  notebookId?: string;
  readOnly?: boolean;
  readOnlyExpr?: string;
  required?: boolean;
  requiredExpr?: string;
  invisibleExpr?: string;
  widget?: string;
  widgetParams?: any;
  overrideLabel?: string;
  label?: string;
  disabled?: boolean;
  originalField?: FormField;
  help?: string;
  // Filtrage générique et dynamique des options d'un champ FK par un champ frère du même
  // formulaire (ex: address_city_id filtré par address_zipcode, voir architecture.md §15.R) — à
  // la Odoo (attribut `domain`) : traduit en `dynamicSource` sur SearchableSelect/
  // SearchableMultiSelect (capacité standard des deux widgets), qui refont une requête serveur
  // filtrée à chaque changement du champ source plutôt que de précharger toute la ressource.
  // sourceField : champ dont on lit la valeur courante dans le modèle ; filterQueryParam :
  // paramètre de requête à passer à l'endpoint liste générique (déjà filtrable par n'importe
  // quelle colonne, voir generic.py::_apply_domain). recordIdQueryParam (optionnel) : ajoute un
  // second paramètre de requête statique portant l'id de l'enregistrement en cours d'édition
  // (widgetParams.recordId, injecté par GenericWizard.vue pour tout champ d'étape) — nécessaire
  // quand la ressource filtrée dépend à la fois d'un champ frère ET de l'enregistrement lui-même
  // (ex: composition_mode_options, qui a besoin du mapping ET du cours en cours de décomposition).
  dynamicOptionsFilter?: { sourceField: string; filterQueryParam: string; recordIdQueryParam?: string };
}
const markdownCache = new Map<string, string>();
function renderMarkdown(md: string | undefined): string {
  if (!md) return '';
  if (markdownCache.has(md)) return markdownCache.get(md)!;
  let html = md;
  html = html.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  
  // Echap HTML pour securite
  html = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Inline markdown
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  
  // Listes et retours ligne
  const lines = html.split('\n');
  let inList = false;
  const processedLines: string[] = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const content = trimmed.substring(2);
      if (!inList) {
        inList = true;
        processedLines.push('<ul><li>' + content + '</li>');
      } else {
        processedLines.push('<li>' + content + '</li>');
      }
    } else {
      if (inList) {
        inList = false;
        processedLines.push('</ul>');
      }
      processedLines.push(trimmed + (i < lines.length - 1 && trimmed ? '<br/>' : ''));
    }
  }
  if (inList) {
    processedLines.push('</ul>');
  }
  
  const result = processedLines.join('\n');
  markdownCache.set(md, result);
  return result;
}

interface FormConfig {
  editableForm?: boolean;
  deletable?: boolean;
  fields?: any[];
  // Ouvre automatiquement ce wizard (id d'une entrée de __actions__) dès que l'enregistrement et
  // la liste des actions sont chargés — pour une feuille de menu "action" pure (ex: un wizard
  // TransientModel singleton) où l'écran intermédiaire du formulaire n'a pas d'intérêt propre :
  // voir autoOpenActionId ci-dessous.
  autoOpenActionId?: string;
}

const props = defineProps<{
  title: string;
  fields: FormField[];
  modelValue: Record<string, any>;
  inline?: boolean;
  formConfig?: FormConfig;
  selectedRecords?: any[];
  resourceKey?: string;
  // Libellé du bouton de soumission (défaut "Enregistrer") — utilisé par GenericWizard.vue, qui
  // réutilise GenericForm tel quel pour rendre chaque étape, avec un libellé propre à l'étape
  // ("Suivant", "Générer l'aperçu", "Enregistrer définitivement"...).
  submitLabel?: string;
  // N'affiche ni le formulaire ni son en-tête/boutons — seule la popin du wizard (déclenchée par
  // formConfig.autoOpenActionId) reste visible. Pour une action de menu pure qui ne doit rien
  // changer à l'écran tant que le wizard n'est pas ouvert (voir App.vue, onTriggerAction).
  headless?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void;
  (e: 'submit', value: Record<string, any>): void;
  (e: 'cancel'): void;
  (e: 'delete', value: Record<string, any>): void;
  // Relayé tel quel depuis GenericWizard.vue (voir startsBackgroundJob) — App.vue l'écoute pour
  // démarrer le polling de progression (loading + checkStatus) quand le wizard soumis vient de
  // lancer une résolution asynchrone en arrière-plan.
  (e: 'wizard-success', payload: { startsBackgroundJob: boolean }): void;
}>();

const notificationStore = useNotificationStore();

// Ouverture automatique du wizard désigné par formConfig.autoOpenActionId (voir FormConfig) —
// déclenchée une seule fois par enregistrement chargé (identité de props.modelValue : App.vue
// assigne un nouvel objet à chaque visite de la feuille, ce qui permet de rouvrir le wizard si
// l'utilisateur revient sur cette feuille après l'avoir annulé/fermé).
let autoOpenedForModel: any = null;
watch(
  () => [props.formConfig?.autoOpenActionId, props.modelValue, modelActions.value] as const,
  ([actionId, model, actions]) => {
    if (!actionId || !model?.id || autoOpenedForModel === model) return;
    const action = (actions || []).find((a: any) => a.id === actionId);
    if (action) {
      autoOpenedForModel = model;
      handleActionClick(action);
    }
  },
  { immediate: true }
);

watch(() => props.resourceKey, async (newKey) => {
  if (newKey) {
    try {
      modelActions.value = await api.fetchGenericActions(newKey);
    } catch (e) {
      console.warn("Could not fetch actions for", newKey, e);
      modelActions.value = [];
    }
  } else {
    modelActions.value = [];
  }
}, { immediate: true });

const isEditableForm = computed(() => {
  return props.formConfig?.editableForm !== false;
});

const isDeletableForm = computed(() => {
  return props.formConfig?.deletable !== false;
});

// Onglet actif de chaque notebook (clé = LayoutElement.notebookId), piloté depuis l'extérieur des
// composants NotebookLayout eux-mêmes (contrairement à leur ancien ref() local) — nécessaire pour
// que handleSubmit() puisse basculer automatiquement sur l'onglet contenant un champ requis resté
// vide (voir validateRequiredFields), y compris s'il n'est pas l'onglet actif au moment de la
// soumission (un onglet non actif n'est pas rendu dans le DOM, voir NotebookLayout, donc aucune
// validation HTML5 native ne peut le couvrir).
const notebookActiveIndex = reactive<Record<string, number>>({});

// Remis à zéro au début de chaque (re)calcul de layoutTree ci-dessous — les ids générés restent
// stables pour la durée d'un calcul, seul repère dont notebookActiveIndex a besoin.
let notebookIdCounter = 0;

function parseLayoutElement(elem: any): LayoutElement | null {
  if (!elem) return null;
  
  if (typeof elem === 'string') {
    const original = props.fields.find(f => f.key === elem);
    if (original && !original.hidden) {
      return {
        type: 'field',
        key: elem,
        label: original.label,
        required: original.required === true,
        requiredExpr: original.requiredExpr,
        disabled: false,
        readOnlyExpr: original.readOnlyExpr,
        invisibleExpr: original.invisibleExpr,
        widget: original.widget,
        widgetParams: original.widgetParams,
        originalField: original,
        help: original.help
      };
    }
    return null;
  }

  // Si c'est un objet simple sans type mais avec une key, c'est un champ
  if (elem.key && !elem.type) {
    const original = props.fields.find(f => f.key === elem.key);
    if (original && !original.hidden) {
      return {
        type: 'field',
        key: elem.key,
        label: elem.overrideLabel || original.label,
        required: elem.required === true || original.required === true,
        requiredExpr: typeof elem.required === 'string' ? elem.required : (typeof elem.requiredExpr === 'string' ? elem.requiredExpr : original.requiredExpr),
        disabled: elem.readOnly === true,
        readOnlyExpr: typeof elem.readOnly === 'string' ? elem.readOnly : (typeof elem.readOnlyExpr === 'string' ? elem.readOnlyExpr : original.readOnlyExpr),
        invisibleExpr: typeof elem.invisibleExpr === 'string' ? elem.invisibleExpr : original.invisibleExpr,
        widget: elem.widget || original.widget,
        widgetParams: elem.widgetParams || original.widgetParams,
        originalField: original,
        help: elem.help || original.help,
        dynamicOptionsFilter: elem.dynamicOptionsFilter
      };
    }
  }

  if (elem.type === 'field') {
    const original = props.fields.find(f => f.key === elem.key);
    if (original && !original.hidden) {
      return {
        type: 'field',
        key: elem.key,
        label: elem.overrideLabel || original.label,
        required: elem.required === true || original.required === true,
        requiredExpr: typeof elem.required === 'string' ? elem.required : (typeof elem.requiredExpr === 'string' ? elem.requiredExpr : original.requiredExpr),
        disabled: elem.readOnly === true,
        readOnlyExpr: typeof elem.readOnly === 'string' ? elem.readOnly : (typeof elem.readOnlyExpr === 'string' ? elem.readOnlyExpr : original.readOnlyExpr),
        invisibleExpr: typeof elem.invisibleExpr === 'string' ? elem.invisibleExpr : original.invisibleExpr,
        widget: elem.widget || original.widget,
        widgetParams: elem.widgetParams || original.widgetParams,
        originalField: original,
        help: elem.help || original.help,
        dynamicOptionsFilter: elem.dynamicOptionsFilter
      };
    }
  }

  if (elem.type === 'group') {
    const children: LayoutElement[] = [];
    if (Array.isArray(elem.children)) {
      elem.children.forEach((child: any) => {
        const parsed = parseLayoutElement(child);
        if (parsed) children.push(parsed);
      });
    }
    return {
      type: 'group',
      string: elem.string,
      col: elem.col || 2,
      span: elem.span,
      children
    };
  }

  if (elem.type === 'separator') {
    return {
      type: 'separator',
      string: elem.string
    };
  }

  if (elem.type === 'newline') {
    return {
      type: 'newline'
    };
  }

  // Layout à onglets façon Odoo (voir architecture.md) : un 'notebook' contient une liste de
  // 'page', chacune pouvant elle-même contenir n'importe quel autre élément de layout (field,
  // group, notebook imbriqué...) — même récursion générique que 'group' ci-dessus, donc
  // l'imbrication (un groupe dans un onglet, un onglet dans un groupe) fonctionne nativement
  // sans code supplémentaire.
  if (elem.type === 'notebook') {
    const children: LayoutElement[] = [];
    if (Array.isArray(elem.children)) {
      elem.children.forEach((child: any) => {
        const parsed = parseLayoutElement(child);
        if (parsed) children.push(parsed);
      });
    }
    return {
      type: 'notebook',
      notebookId: `nb-${notebookIdCounter++}`,
      children
    };
  }

  if (elem.type === 'page') {
    const children: LayoutElement[] = [];
    if (Array.isArray(elem.children)) {
      elem.children.forEach((child: any) => {
        const parsed = parseLayoutElement(child);
        if (parsed) children.push(parsed);
      });
    }
    return {
      type: 'page',
      string: elem.string,
      children
    };
  }

  return null;
}


const layoutTree = computed<LayoutElement[]>(() => {
  notebookIdCounter = 0;
  if (props.formConfig?.fields && props.formConfig.fields.length > 0) {
    const parsed: LayoutElement[] = [];
    props.formConfig.fields.forEach((item: any) => {
      const parsedItem = parseLayoutElement(item);
      if (parsedItem) parsed.push(parsedItem);
    });
    return parsed;
  }

  // Fallback par défaut : tous les champs dans un layout plat — hidden exclu, symétrique avec
  // GenericList.vue/App.vue/GenericListModal.vue (voir architecture.md, section E) : un champ
  // calculé qui n'existe que pour nourrir le readOnlyExpr d'un AUTRE champ ne doit jamais devenir
  // son propre champ de formulaire, qu'il ait été filtré en amont par l'appelant ou non — ce
  // composant ne doit pas dépendre de la discipline de CHAQUE appelant pour rester correct.
  return props.fields.filter(f => !f.hidden).map(f => ({
    type: 'field',
    key: f.key,
    label: f.label,
    required: f.required === true,
    requiredExpr: f.requiredExpr,
    disabled: false,
    readOnlyExpr: f.readOnlyExpr,
    invisibleExpr: f.invisibleExpr,
    widget: f.widget,
    widgetParams: f.widgetParams,
    originalField: f,
    help: f.help,
    // Absent jusqu'ici de ce fallback (contrairement à parseLayoutElement ci-dessus) : un champ FK
    // à dynamicOptionsFilter déclaré directement sur le field (cas de tout wizard, voir
    // GenericWizard.vue qui ne passe jamais de formConfig.fields explicite) atterrissait toujours
    // ici sans jamais activer le filtre dynamique.
    dynamicOptionsFilter: f.dynamicOptionsFilter
  }));
});

// Déclarer localement le composant récursif de rendu avec h() pour éviter les limitations du compilateur de template
const FormLayoutGrid: any = defineComponent({
  name: 'FormLayoutGrid',
  props: {
    elements: {
      type: Array as () => LayoutElement[],
      required: true
    },
    localModel: {
      type: Object as () => Record<string, any>,
      required: true
    },
    isEditableForm: {
      type: Boolean,
      required: true
    },
    inline: {
      type: Boolean,
      default: false
    },
    isNested: {
      type: Boolean,
      default: false
    },
    isMultiEdit: {
      type: Boolean,
      default: false
    },
    initialModelValue: {
      type: Object as () => Record<string, any>,
      default: () => ({})
    }
  },
  setup(gridProps) {
    return () => {
      // Si inline : max-content 1fr
      // Si non inline : max-content 1fr max-content 1fr
      const gridTemplate = gridProps.inline
        ? 'max-content 1fr'
        : 'max-content 1fr max-content 1fr';

      const isDivergent = (key: string) => {
        return gridProps.isMultiEdit && gridProps.initialModelValue[key] === undefined;
      };

      const isModified = (key: string) => {
        if (!gridProps.isMultiEdit) return false;
        const current = gridProps.localModel[key];
        const initial = gridProps.initialModelValue[key];
        if (current === undefined && initial === undefined) return false;
        return current !== initial;
      };

      return h('div', {
        class: 'fields-layout-container',
        style: gridProps.isNested ? {
          display: 'contents'
        } : {
          display: 'grid',
          gridTemplateColumns: gridTemplate,
          gap: '10px',
          alignItems: 'center',
          width: '100%'
        }
      },
        gridProps.elements.flatMap(elem => {
          if (elem.type === 'newline') {
            return [ h('div', {
              class: 'form-layout-newline',
              style: {
                gridColumn: '1 / -1',
                height: '0',
                width: '100%',
                margin: '0',
                padding: '0'
              }
            }) ];
          }

          if (elem.type === 'separator') {
            return [
              h('div', {
                class: 'form-layout-separator',
                style: {
                  gridColumn: '1 / -1',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                  margin: '0',
                  width: '100%'
                }
              }, [
                elem.string ? h('span', { class: 'separator-title' }, elem.string) : null,
                h('hr', { class: 'separator-hr' })
              ])
            ];
          }

          if (elem.type === 'group') {
            const cols = elem.col || (gridProps.inline ? 1 : 2);
            const groupGridTemplate = Array(cols).fill('max-content 1fr').join(' ');
            let gridCol = '1 / -1';
            if (elem.span) {
              gridCol = `span ${elem.span * 2}`;
            }
            return [
              h('div', {
                class: 'form-layout-group',
                style: {
                  display: 'grid',
                  gridTemplateColumns: groupGridTemplate,
                  gap: '10px',
                  gridColumn: gridCol,
                  alignItems: 'center',
                  margin: '0',
                  padding: '8px 12px',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px dashed var(--border-color)',
                  borderRadius: '6px'
                }
              }, [
                elem.string ? h('h4', {
                  class: 'group-title',
                  style: {
                    gridColumn: '1 / -1',
                    fontSize: '13px',
                    fontWeight: '700',
                    color: 'var(--accent-primary)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.7px',
                    margin: '0',
                    paddingLeft: '8px',
                    borderLeft: '3px solid var(--accent-primary)'
                  }
                }, elem.string) : null,
                h(FormLayoutGrid, {
                  elements: elem.children || [],
                  localModel: gridProps.localModel,
                  isEditableForm: gridProps.isEditableForm,
                  inline: gridProps.inline,
                  isNested: true,
                  isMultiEdit: gridProps.isMultiEdit,
                  initialModelValue: gridProps.initialModelValue
                })
              ])
            ];
          }

          if (elem.type === 'notebook') {
            return [
              h(NotebookLayout, {
                notebookId: elem.notebookId,
                pages: elem.children || [],
                localModel: gridProps.localModel,
                isEditableForm: gridProps.isEditableForm,
                inline: gridProps.inline,
                isMultiEdit: gridProps.isMultiEdit,
                initialModelValue: gridProps.initialModelValue
              })
            ];
          }

          if (elem.type === 'field' && elem.originalField) {
            const field = elem.originalField;
            const key = elem.key!;

            let evaluatedInvisible = false;
            if (elem.invisibleExpr) {
              try {
                const fn = new Function('model', `return ${elem.invisibleExpr}`);
                evaluatedInvisible = !!fn(gridProps.localModel);
              } catch (e) {
                console.error("Error evaluating invisible expression", e);
              }
            }
            if (evaluatedInvisible) {
              return [];
            }

            let evaluatedRequired = false;
            if (elem.requiredExpr) {
              try {
                const fn = new Function('model', `return ${elem.requiredExpr}`);
                evaluatedRequired = !!fn(gridProps.localModel);
              } catch (e) {
                console.error("Error evaluating required expression", e);
              }
            }
            const required = (elem.required === true) || evaluatedRequired;

            let evaluatedDisabled = false;
            if (elem.readOnlyExpr) {
              try {
                const fn = new Function('model', `return ${elem.readOnlyExpr}`);
                evaluatedDisabled = !!fn(gridProps.localModel);
              } catch (e) {
                console.error("Error evaluating readOnly expression", e);
              }
            }
            const disabled = gridProps.isEditableForm === false || elem.disabled === true || evaluatedDisabled;
            const label = elem.label || field.label;

            const isFull = field.fullWidth === true;
            const inputStyle = {
              gridColumn: (isFull && !gridProps.inline) ? 'span 3' : 'auto'
            };

            let inputElement: any = null;

            const isFk = !!field.resource;
            // Capacité standard des widgets many2one/many2many (SearchableSelect/
            // SearchableMultiSelect, voir architecture.md §15.R) — options recherchées côté
            // serveur plutôt que préchargées, dès qu'un champ FK déclare dynamicOptionsFilter
            // dans ui.json. undefined pour tout champ FK qui n'en déclare pas : comportement
            // strictement inchangé.
            const dynamicSource = elem.dynamicOptionsFilter ? {
              resource: field.resource!,
              filterQueryParam: elem.dynamicOptionsFilter.filterQueryParam,
              filterValue: gridProps.localModel[elem.dynamicOptionsFilter.sourceField],
              // recordIdQueryParam : second filtre statique (l'enregistrement en cours d'édition
              // lui-même, pas un champ frère) — voir LayoutElement.dynamicOptionsFilter plus haut.
              // widgetParams.recordId est injecté par GenericWizard.vue pour tout champ d'étape ;
              // absent hors contexte wizard, où recordIdQueryParam n'est de toute façon jamais
              // déclaré aujourd'hui.
              ...(elem.dynamicOptionsFilter.recordIdQueryParam ? {
                recordIdQueryParam: elem.dynamicOptionsFilter.recordIdQueryParam,
                recordId: elem.widgetParams?.recordId,
              } : {}),
            } : undefined;

            const widgetComponent = getWidgetForContext(elem.widget, 'form');
            if (widgetComponent) {
              // Contrat commun à tout widget du registre (voir widgets/registry.ts) : la forme de
              // modelValue dépend du widget (liste d'IDs pour many2many_ordered_list, objet
              // composite pour un widget de wizard...) — chaque widget est responsable de sa
              // propre valeur par défaut, pas de coercion générique ici.
              inputElement = h(widgetComponent, {
                modelValue: gridProps.localModel[key],
                field: field,
                widgetParams: elem.widgetParams,
                disabled: disabled,
                parentRecord: gridProps.localModel,
                style: inputStyle,
                'onUpdate:modelValue': (val: any) => {
                  gridProps.localModel[key] = val;
                }
              });
            } else if (field.resource && field.parentField) {
              // Relation 1-à-N "possédée" (voir generic.py::parentField, architecture.md) : jamais
              // un picker multiselect classique — les enregistrements ciblés n'existent pas
              // indépendamment de ce record (ex: attacher une Partition d'une autre Division
              // échouerait côté serveur, son modèle interdisant de réassigner sa FK parent).
              // Vérifié avant "multiselect" ci-dessous car un champ _ids possédé porte le même
              // ui_type que le multiselect dans le schéma — c'est resource+parentField qui les
              // distingue, pas le type. Même widget partagé que GenericList.vue (tags + crayon).
              inputElement = h(OwnedRelationField, {
                modelValue: gridProps.localModel[key],
                field: field,
                widgetParams: elem.widgetParams,
                disabled: disabled,
                parentRecord: gridProps.localModel,
                style: inputStyle,
                'onUpdate:modelValue': (val: any) => {
                  gridProps.localModel[key] = val;
                }
              });
            } else if (field.type === 'multiselect') {
              const options = field.options || [];
              inputElement = h(SearchableMultiSelect, {
                modelValue: Array.isArray(gridProps.localModel[key]) ? gridProps.localModel[key] : (gridProps.localModel[key] ? [gridProps.localModel[key]] : []),
                options: options,
                dynamicSource: dynamicSource,
                disabled: disabled,
                placeholder: isDivergent(key) && !isModified(key) ? 'Valeurs différentes' : field.placeholder,
                required: required && !gridProps.isMultiEdit,
                style: inputStyle,
                'onUpdate:modelValue': (val: any) => {
                  gridProps.localModel[key] = val;
                },
                onChange: (val: any) => {
                  gridProps.localModel[key] = val;
                }
              });
            } else if (isFk) {
              // Auto-exclusion d'un champ FK auto-référent (ex: Classroom.parent_classroom_id,
              // Course.parent_id) : un enregistrement ne peut jamais se désigner lui-même comme
              // son propre parent — exclu des options plutôt que laissé au seul rejet serveur
              // tardif (@constrains côté backend, voir classroom.py::_validate_and_sync_
              // classroom_tree). Ne couvre que le cas direct (soi-même) : un cycle indirect via un
              // descendant reste seulement rejeté côté serveur, pas filtré ici (voir plan salles
              // §5, risque #7 — choix délibéré, pas une limite oubliée).
              const options = (field.resource === props.resourceKey && gridProps.localModel.id != null)
                ? (field.options || []).filter((o: any) => String(o.value) !== String(gridProps.localModel.id))
                : (field.options || []);
              inputElement = h(SearchableSelect, {
                modelValue: gridProps.localModel[key] !== undefined && gridProps.localModel[key] !== null ? gridProps.localModel[key] : null,
                options: options,
                dynamicSource: dynamicSource,
                disabled: disabled,
                placeholder: isDivergent(key) && !isModified(key) ? 'Valeurs différentes' : field.placeholder,
                required: required && !gridProps.isMultiEdit,
                nullable: field.nullable,
                style: inputStyle,
                'onUpdate:modelValue': (val: any) => {
                  gridProps.localModel[key] = val;
                },
                onChange: (val: any) => {
                  gridProps.localModel[key] = val;
                }
              });
            } else if (field.type === 'text') {
              inputElement = h('input', {
                type: 'text',
                class: [
                  'form-input',
                  isDivergent(key) && !isModified(key) ? 'form-input-divergent' : '',
                  isModified(key) ? 'form-input-modified' : ''
                ],
                style: inputStyle,
                value: gridProps.localModel[key] !== undefined && gridProps.localModel[key] !== null ? gridProps.localModel[key] : '',
                required: required && !gridProps.isMultiEdit,
                disabled: disabled,
                placeholder: isDivergent(key) && !isModified(key)
                  ? '(Valeurs multiples - Saisir pour modifier)'
                  : (field.placeholder || ''),
                onInput: (e: Event) => {
                  gridProps.localModel[key] = (e.target as HTMLInputElement).value;
                }
              });
            } else if (field.type === 'number') {
              inputElement = h('input', {
                type: 'number',
                class: [
                  'form-input',
                  isDivergent(key) && !isModified(key) ? 'form-input-divergent' : '',
                  isModified(key) ? 'form-input-modified' : ''
                ],
                style: inputStyle,
                value: gridProps.localModel[key] !== undefined && gridProps.localModel[key] !== null ? gridProps.localModel[key] : '',
                required: required && !gridProps.isMultiEdit,
                disabled: disabled,
                min: field.min,
                max: field.max,
                step: field.step || '1',
                placeholder: isDivergent(key) && !isModified(key) ? 'Valeurs différentes' : '',
                onInput: (e: Event) => {
                  const val = (e.target as HTMLInputElement).value;
                  gridProps.localModel[key] = val !== '' ? Number(val) : null;
                }
              });
            } else if (field.type === 'date') {
              inputElement = h('input', {
                type: 'date',
                class: [
                  'form-input',
                  isDivergent(key) && !isModified(key) ? 'form-input-divergent' : '',
                  isModified(key) ? 'form-input-modified' : ''
                ],
                style: inputStyle,
                value: gridProps.localModel[key] || '',
                required: required && !gridProps.isMultiEdit,
                disabled: disabled,
                onInput: (e: Event) => {
                  gridProps.localModel[key] = (e.target as HTMLInputElement).value;
                }
              });
            } else if (field.type === 'boolean') {
              inputElement = h('div', {
                class: 'toggle-wrapper',
                style: inputStyle
              }, [
                h(BaseToggle, {
                  modelValue: !!gridProps.localModel[key],
                  disabled: disabled,
                  isDivergent: isDivergent(key) && !isModified(key),
                  isModified: isModified(key),
                  'onUpdate:modelValue': (val: boolean) => {
                    gridProps.localModel[key] = val;
                  }
                }),
                h('span', {
                  class: [
                    'toggle-status',
                    isDivergent(key) && !isModified(key) ? 'status-divergent' : ''
                  ]
                }, gridProps.localModel[key] === undefined ? 'Divergent (cliquez pour cocher)' : (gridProps.localModel[key] ? 'Oui' : 'Non'))
              ]);
            } else if (field.type === 'select') {
              inputElement = h('select', {
                class: [
                  'select-custom form-select',
                  isDivergent(key) && !isModified(key) ? 'form-select-divergent' : '',
                  isModified(key) ? 'form-select-modified' : ''
                ],
                style: inputStyle,
                value: gridProps.localModel[key] !== undefined && gridProps.localModel[key] !== null ? gridProps.localModel[key] : '',
                required: required && !gridProps.isMultiEdit,
                disabled: disabled,
                onChange: (e: Event) => {
                  const val = (e.target as HTMLSelectElement).value;
                  if (val === '') {
                    gridProps.localModel[key] = null;
                  } else {
                    const num = Number(val);
                    gridProps.localModel[key] = isNaN(num) ? val : num;
                  }
                }
              }, [
                // Pas d'option vide pour un champ non-nullable (voir SearchableSelect.vue) : la
                // choisir enverrait null, silencieusement ignoré par clean_payload côté backend
                // — seule une vraie option (déjà présente dans field.options, ex: "Aucune") l'est.
                field.nullable !== false
                  ? h('option', { value: '' }, isDivergent(key) && !isModified(key) ? '-- Divergent (Modifier) --' : '-- Choisir --')
                  : null,
                ...(field.options || []).map(opt =>
                  h('option', { value: opt.value }, opt.label)
                )
              ]);
            } else if (field.type === 'color') {
              inputElement = h('div', {
                class: [
                  'form-color-swatch-wrapper',
                  disabled ? 'readonly-swatch' : '',
                  isDivergent(key) && !isModified(key) ? 'color-swatch-divergent' : '',
                  isModified(key) ? 'color-swatch-modified' : ''
                ],
                style: inputStyle
              }, [
                h(ColorSwatchPicker, {
                  modelValue: gridProps.localModel[key] !== undefined ? gridProps.localModel[key] : '',
                  onChange: (val: string) => {
                    gridProps.localModel[key] = val;
                  }
                }),
                isDivergent(key) && !isModified(key)
                  ? h('span', { class: 'color-divergent-text' }, 'Divergent (cliquez pour choisir)')
                  : null
              ]);
            } else if (field.type === 'duration') {
              inputElement = h(DurationInput, {
                modelValue: gridProps.localModel[key] !== undefined ? gridProps.localModel[key] : null,
                disabled: disabled,
                includeZero: (field as any).durationIncludeZero,
                style: inputStyle,
                onChange: (val: number | null) => {
                  gridProps.localModel[key] = val;
                }
              });
            } else if (field.type === 'html') {
              // Contenu HTML formaté en lecture seule (ex: message d'info/de confirmation d'un
              // wizard) — jamais un input, aucune valeur remontée dans localModel.
              inputElement = h('div', {
                class: 'form-html-content',
                style: inputStyle,
                innerHTML: gridProps.localModel[key] || ''
              });
            } else if (field.type === 'json') {
              // Champ objet calculé côté serveur (ex: Course.underventilated_resource_ids) :
              // jamais un input texte brut sur un objet JS — juste un résumé compact en lecture
              // seule, avec le détail en tooltip. Toujours read-only (pas de widget d'édition
              // générique sensé pour un JSON arbitraire).
              const val = gridProps.localModel[key];
              const hasValue = val && typeof val === 'object' && Object.keys(val).length > 0;
              inputElement = h('div', {
                class: 'form-json-summary',
                style: inputStyle,
                title: hasValue ? JSON.stringify(val, null, 2) : ''
              }, hasValue ? `${Object.keys(val).length} type(s) de ressource` : '—');
            } else if (field.type === 'binary') {
              // Widget par défaut de tout champ binaire (n'importe quel fichier) sans widget
              // explicite déclaré — voir BinaryFileField.vue. Un champ binaire avec
              // info={"widget": "image"} ne passe jamais ici : il est intercepté plus haut par
              // getWidgetForContext (registry.ts), qui rend ImageField à la place.
              inputElement = h(BinaryFileField, {
                modelValue: gridProps.localModel[key],
                disabled: disabled,
                style: inputStyle,
                'onUpdate:modelValue': (val: any) => {
                  gridProps.localModel[key] = val;
                }
              });
            }

            const labelElement = h('label', {
              class: 'form-label',
              for: key,
              style: {
                gridColumn: 'auto',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: '2px'
              }
            }, [
              h('span', {
                style: {
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px'
                }
              }, [
                h('span', {}, label),
                required ? h('span', { class: 'required-indicator' }, ' *') : null,
                elem.help ? h(BaseTooltip, { htmlContent: renderMarkdown(elem.help) }) : null
              ]),
              isModified(key) ? h('span', { class: 'field-modified-badge', style: { marginLeft: '0px', marginTop: '4px' } }, '✏️ Modifié') : null
            ]);

            return [ labelElement, inputElement ];
          }

          return [];
        })
      );
    };
  }
});

// Layout à onglets (voir architecture.md, layout notebook/page) : contrairement à 'group', qui
// délègue directement à une instance imbriquée de FormLayoutGrid, un notebook a besoin d'un état
// local réactif (l'onglet actif) — impossible à porter dans FormLayoutGrid elle-même, qui rend
// D'UN SEUL COUP tous les éléments de son tableau `elements` dans une seule fonction de rendu
// partagée (pas d'instance de composant séparée par élément). D'où ce composant dédié, avec son
// propre setup()/ref() — même mécanisme que 'group' pour le rendu de la page active (délégation à
// FormLayoutGrid), simplement précédé d'une barre d'onglets qui pilote quelle page est affichée.
const NotebookLayout: any = defineComponent({
  name: 'NotebookLayout',
  props: {
    notebookId: {
      type: String,
      default: ''
    },
    pages: {
      type: Array as () => LayoutElement[],
      required: true
    },
    localModel: {
      type: Object as () => Record<string, any>,
      required: true
    },
    isEditableForm: {
      type: Boolean,
      required: true
    },
    inline: {
      type: Boolean,
      default: false
    },
    isMultiEdit: {
      type: Boolean,
      default: false
    },
    initialModelValue: {
      type: Object as () => Record<string, any>,
      default: () => ({})
    }
  },
  setup(notebookProps) {
    // Contrôlé via le registre partagé notebookActiveIndex (clé = notebookId) plutôt qu'un ref()
    // local — permet à handleSubmit() de basculer l'onglet actif depuis l'extérieur de ce
    // composant (voir déclaration de notebookActiveIndex plus haut).
    const activeIndex = computed({
      get: () => notebookActiveIndex[notebookProps.notebookId] ?? 0,
      set: (v: number) => { notebookActiveIndex[notebookProps.notebookId] = v; }
    });
    return () => {
      const pages = notebookProps.pages || [];
      if (activeIndex.value >= pages.length) activeIndex.value = 0;
      const activePage = pages[activeIndex.value];

      return h('div', {
        class: 'form-notebook',
        style: { gridColumn: '1 / -1', width: '100%' }
      }, [
        h('div', { class: 'form-notebook-tabs' }, pages.map((page, i) =>
          h('button', {
            type: 'button',
            class: ['form-notebook-tab', i === activeIndex.value ? 'form-notebook-tab-active' : ''],
            onClick: (e: Event) => {
              e.preventDefault();
              activeIndex.value = i;
            }
          }, page.string || `Onglet ${i + 1}`)
        )),
        h('div', {
          class: 'form-notebook-page',
          style: {
            display: 'grid',
            gridTemplateColumns: notebookProps.inline ? 'max-content 1fr' : 'max-content 1fr max-content 1fr',
            gap: '10px',
            alignItems: 'center',
            width: '100%'
          }
        }, activePage ? [
          h(FormLayoutGrid, {
            elements: activePage.children || [],
            localModel: notebookProps.localModel,
            isEditableForm: notebookProps.isEditableForm,
            inline: notebookProps.inline,
            isNested: true,
            isMultiEdit: notebookProps.isMultiEdit,
            initialModelValue: notebookProps.initialModelValue
          })
        ] : [])
      ]);
    };
  }
});

// Copie locale réactive pour éviter de modifier directement le modèle parent avant soumission
const localModel = ref<Record<string, any>>({});
const initialModelValue = ref<Record<string, any>>({});

const isMultiEdit = computed(() => {
  return props.selectedRecords && props.selectedRecords.length > 1;
});

// Validation générique des champs requis (required=true ou requiredExpr, voir LayoutElement) au
// moment de la soumission — nécessaire en plus de la validation HTML5 native des <input required>
// (GenericForm.vue plus bas) car un widget en collection (OwnedRelationField, "au moins une ligne
// requise" — voir Teacher.discipline_lines) ne porte aucun <input> natif à valider, et un champ
// placé sur un onglet notebook non actif n'est même pas rendu dans le DOM (voir NotebookLayout) :
// la validation native ne peut couvrir ni l'un ni l'autre cas. L'erreur est signalée via le store
// de notification partagé (déjà utilisé pour toute erreur de sauvegarde, voir App.vue/
// GenericListModal.vue/Many2ManyOrderedList.vue) plutôt qu'une bannière dédiée à ce formulaire.

function isValueEmpty(value: any): boolean {
  if (Array.isArray(value)) return value.length === 0;
  return value === null || value === undefined || value === '';
}

function evaluateRequired(elem: LayoutElement, model: Record<string, any>): boolean {
  if (elem.required) return true;
  if (elem.requiredExpr) {
    try {
      const fn = new Function('model', `return ${elem.requiredExpr}`);
      return !!fn(model);
    } catch (e) {
      console.error("Error evaluating required expression", e);
      return false;
    }
  }
  return false;
}

interface NotebookTabRef { notebookId: string; pageIndex: number; }

// Parcourt TOUTES les pages de TOUS les notebooks (pas seulement l'onglet actif) puisqu'un champ
// requis peut être caché sur un onglet non consulté par l'utilisateur — accumule le chemin des
// onglets ancêtres traversés pour pouvoir les rendre actifs d'un coup si ce champ est en défaut.
function findFirstInvalidRequiredField(
  elements: LayoutElement[],
  model: Record<string, any>,
  path: NotebookTabRef[] = []
): { key: string; label: string; path: NotebookTabRef[] } | null {
  for (const elem of elements) {
    if (elem.type === 'field' && elem.key) {
      if (evaluateRequired(elem, model) && isValueEmpty(model[elem.key])) {
        return { key: elem.key, label: elem.label || elem.key, path };
      }
    } else if (elem.type === 'group' && elem.children) {
      const found = findFirstInvalidRequiredField(elem.children, model, path);
      if (found) return found;
    } else if (elem.type === 'notebook' && elem.children) {
      for (let pageIndex = 0; pageIndex < elem.children.length; pageIndex++) {
        const page = elem.children[pageIndex];
        const found = findFirstInvalidRequiredField(page.children || [], model, [...path, { notebookId: elem.notebookId || '', pageIndex }]);
        if (found) return found;
      }
    }
  }
  return null;
}

// Retourne false et bascule sur l'onglet en défaut si un champ requis est vide — appelé en tête de
// handleSubmit(). Ignoré en édition groupée (isMultiEdit) : seuls les champs explicitement
// modifiés y sont soumis (payload partiel), un champ requis peut légitimement rester non touché
// pour la plupart des enregistrements sélectionnés.
function validateRequiredFields(): boolean {
  if (isMultiEdit.value) return true;
  const invalid = findFirstInvalidRequiredField(layoutTree.value, localModel.value);
  if (!invalid) return true;
  for (const ref of invalid.path) {
    notebookActiveIndex[ref.notebookId] = ref.pageIndex;
  }
  notificationStore.showNotification('error', `Le champ « ${invalid.label} » est obligatoire.`);
  return false;
}

let oldLocalModelStr = '';
let onchangeTimeout: ReturnType<typeof setTimeout> | null = null;

function initializeModel() {
  if (isMultiEdit.value) {
    const model: Record<string, any> = {};
    props.fields.forEach(field => {
      const key = field.key;
      if (!props.selectedRecords || props.selectedRecords.length === 0) return;
      const firstVal = props.selectedRecords[0][key];
      const isIdentical = props.selectedRecords.every(rec => rec[key] === firstVal);
      if (isIdentical) {
        model[key] = firstVal;
      } else {
        model[key] = undefined;
      }
    });
    localModel.value = model;
    initialModelValue.value = JSON.parse(JSON.stringify(model));
  } else {
    const cleanNewVal = props.modelValue ? { ...props.modelValue } : {};
    
    localModel.value = cleanNewVal;
    initialModelValue.value = JSON.parse(JSON.stringify(cleanNewVal));
    
    props.fields.forEach(field => {
      if (field.type === 'boolean' && localModel.value[field.key] === undefined) {
        const defaultVal = (field as any).default !== undefined ? (field as any).default : false;
        localModel.value[field.key] = defaultVal;
        initialModelValue.value[field.key] = defaultVal;
      }
      if (field.type === 'color' && !localModel.value[field.key]) {
        const defaultVal = (field as any).default || '#3498DB';
        localModel.value[field.key] = defaultVal;
        initialModelValue.value[field.key] = defaultVal;
      }
      if (field.type === 'select' && localModel.value[field.key] === undefined) {
        const defaultVal = (field as any).default !== undefined ? (field as any).default : null;
        localModel.value[field.key] = defaultVal;
        initialModelValue.value[field.key] = defaultVal;
      }
      // Tous les champs duration existants sont non-nullables avec une valeur par défaut réelle
      // côté backend (voir backend/app/models/*.py) — pas de placeholder "-- Choisir --" dans
      // DurationInput.vue, donc toujours seeder une valeur concrète ici (même motif que select
      // ci-dessus), pour ne jamais laisser localModel[key] undefined le temps qu'un nouvel
      // enregistrement soit soumis.
      if (field.type === 'duration' && localModel.value[field.key] === undefined) {
        const defaultVal = (field as any).default !== undefined ? (field as any).default : 0;
        localModel.value[field.key] = defaultVal;
        initialModelValue.value[field.key] = defaultVal;
      }
      // Un champ multiselect (relation possédée via OwnedRelationField, ou multiselect classique
      // via SearchableMultiSelect, voir FormLayoutGrid) attend toujours un tableau — jamais
      // undefined. Sur un NOUVEL enregistrement (props.modelValue vide), la clé n'existe pas
      // encore dans localModel : sans ce défaut, OwnedRelationField/SearchableMultiSelect
      // reçoivent modelValue=undefined et Vue avertit ("Expected Array, got Undefined"). Même
      // motif que les défauts boolean/color/select/duration ci-dessus.
      if (field.type === 'multiselect' && localModel.value[field.key] === undefined) {
        localModel.value[field.key] = [];
        initialModelValue.value[field.key] = [];
      }
    });
    oldLocalModelStr = JSON.stringify(localModel.value);
  }
}

// Watch props.modelValue et props.selectedRecords pour mettre à jour la copie locale
watch([() => props.modelValue, () => props.selectedRecords], () => {
  initializeModel();
}, { immediate: true, deep: true });

// Synchroniser les saisies locales en temps réel avec le parent pour forcer la réactivité du bouton d'ajout (uniquement hors modification groupée)
watch(localModel, (newVal) => {
  if (isMultiEdit.value) return;
  const newStr = JSON.stringify(newVal);
  if (newStr === JSON.stringify(props.modelValue)) return;
  
  // Identifier le champ qui a changé
  let changedKey: string | null = null;
  const oldObj = oldLocalModelStr ? JSON.parse(oldLocalModelStr) : {};
  for (const k in newVal) {
    if (JSON.stringify(newVal[k]) !== JSON.stringify(oldObj[k])) {
      changedKey = k;
      break;
    }
  }
  
  oldLocalModelStr = newStr;
  emit('update:modelValue', { ...newVal });
  
  // Appel onchange serveur si on connaît le champ modifié
  if (changedKey && props.resourceKey) {
    if (onchangeTimeout) clearTimeout(onchangeTimeout);
    onchangeTimeout = setTimeout(async () => {
      try {
        const response = await api.apiFetch(`/api/generic/${props.resourceKey}/onchange`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            values: localModel.value,
            field_changed: changedKey
          })
        });
        const data = await response.json();
        if (data.status === 'success' && data.diff) {
          let hasChanges = false;
          for (const k in data.diff) {
            if (localModel.value[k] !== data.diff[k]) {
              localModel.value[k] = data.diff[k];
              hasChanges = true;
            }
          }
          if (hasChanges) {
             oldLocalModelStr = JSON.stringify(localModel.value);
             emit('update:modelValue', { ...localModel.value });
          }
        }
      } catch (e) {
        console.error("Erreur lors de l'appel onchange:", e);
      }
    }, 250);
  }
}, { deep: true });

function handleSubmit() {
  if (!validateRequiredFields()) return;
  if (isMultiEdit.value) {
    const submitPayload: Record<string, any> = {};
    props.fields.forEach(field => {
      if (field.resource && field.parentField) return;
      const key = field.key;
      const current = localModel.value[key];
      const initial = initialModelValue.value[key];
      const isFieldModified = (current !== undefined || initial !== undefined) && current !== initial;
      if (isFieldModified) {
        submitPayload[key] = current;
      }
    });
    emit('submit', submitPayload);
  } else {
    initialModelValue.value = JSON.parse(JSON.stringify(localModel.value));
    emit('update:modelValue', localModel.value);
    // Les relations 1-N "possédées" (OwnedRelationField, ex: discipline_line_ids) sont désormais
    // soumises ici avec le reste du formulaire, sous forme de "commandes" à la Odoo (un dict par
    // ligne : {id, ...champs} pour garder/modifier, {...champs} sans id pour créer — tout id
    // rattaché mais absent de la liste est supprimé) plutôt qu'une simple liste d'ids : voir
    // OwnedRelationField.vue (seul écrivain de sa collection, plus aucun appel API direct depuis
    // la popin) et CRUDMixin._apply_owned_collection_commands (base.py, architecture.md 15.J).
    //
    // Restreint à props.fields (+ id) plutôt que localModel.value tel quel : localModel a été
    // initialisé par simple copie du GET (voir le watch sur props.modelValue plus haut), qui
    // inclut aussi les champs calculés en lecture seule (@exposed sans setter, ex: student_ids,
    // weighted_duration_minutes) — jamais déclarés comme champs de CE formulaire. Les réémettre
    // tels quels dans le PATCH n'a jamais de raison d'être (ce ne sont pas des champs éditables
    // ici), et pour un champ sans setter côté backend, ça fait planter CRUDMixin.update() avec une
    // AttributeError brute plutôt qu'une erreur métier claire (bug constaté avec student_ids).
    const submitPayload: Record<string, any> = { id: localModel.value.id };
    props.fields.forEach(field => {
      const key = field.key;
      if (key in localModel.value) {
        submitPayload[key] = localModel.value[key];
      }
    });
    emit('submit', submitPayload);
  }
}

function handleCancel() {
  localModel.value = JSON.parse(JSON.stringify(initialModelValue.value));
  emit('cancel');
}

function handleDelete() {
  emit('delete', localModel.value);
}
</script>

<style>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(10, 12, 16, 0.8);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  animation: fadeIn var(--transition-fast);
}

.generic-form-modal {
  width: 580px;
  max-width: 95%;
  background-color: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  overflow: visible;
  box-shadow: var(--shadow-lg), 0 0 30px rgba(99, 102, 241, 0.15);
  display: flex;
  flex-direction: column;
}

.form-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-surface);
}

.form-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.btn-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 24px;
  cursor: pointer;
  transition: color var(--transition-fast);
  line-height: 1;
}

.btn-close:hover {
  color: var(--text-primary);
}

.form-body {
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-height: 80vh;
  overflow-y: auto;
}



.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.required-indicator {
  color: var(--accent-danger);
  margin-left: 2px;
}

/* Style de base .form-input/.form-select : voir main.css (déplacé pour être garanti disponible
   avant même que GenericForm.vue ait été monté une première fois — SearchableSelect.vue en
   dépend). */
.form-select {
  width: 100%;
}

/* Switch toggle style */
.toggle-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 42px;
}


.toggle-status {
  font-size: 13px;
  color: var(--text-primary);
}

/* Actions */
.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  /* Colle les boutons en bas du panneau quand .form-body a plus de hauteur que son contenu (cas
     du panneau inline, flex:1) — sans effet quand le conteneur (ex: la modale) épouse déjà la
     hauteur du contenu, margin-top:auto n'ayant alors aucun espace où pousser. */
  margin-top: auto;
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.btn-delete {
  margin-right: auto;
}

.glass-morphism {
  background: var(--bg-card);
  backdrop-filter: blur(12px);
}

/* Sélecteur de couleur formulaire — identique à la vue liste */
.form-color-swatch-wrapper {
  width: 100%;
}

.form-html-content {
  width: 100%;
  line-height: 1.5;
  color: var(--text-primary);
}

.form-html-content :deep(p) {
  margin: 0 0 8px 0;
}

.form-html-content :deep(p:last-child) {
  margin-bottom: 0;
}

.form-json-summary {
  width: 100%;
  padding: 10px 14px;
  box-sizing: border-box;
  color: var(--text-secondary);
  font-size: 14px;
  font-style: italic;
  cursor: help;
}

.readonly-swatch {
  pointer-events: none;
  opacity: 0.6;
}

/* Styles pour le mode inline (panneau latéral) */
.inline-form-container {
  width: 100%;
  height: 100%;
  background-color: var(--bg-card);
  border-left: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.generic-form-inline {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.generic-form-inline .form-header {
  background-color: var(--bg-surface);
  border-bottom: 1px solid var(--border-color);
  padding: 14px 20px;
}

.generic-form-inline .form-title {
  color: var(--text-primary);
  font-size: 14px;
}

.generic-form-inline .form-body {
  padding: 10px;
  background-color: var(--bg-card);
  overflow-y: auto;
  flex: 1;
  /* La règle de base .form-body fixe max-height: 80vh pour la modale (dimensionnée par rapport à
     la fenêtre). En panneau latéral, .form-body doit occuper toute la hauteur réelle disponible
     de .generic-form-inline (flex: 1 ci-dessus) — sans ce reset, 80vh (relatif à la fenêtre, pas
     au panneau) tronque .form-body dès que le panneau dépasse 80% de la hauteur de la fenêtre,
     laissant un espace vide en bas du panneau sous lequel le contenu scrollé semble disparaître. */
  max-height: none;
}

.generic-form-inline .form-input,
.generic-form-inline .form-select {
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.generic-form-inline .form-input:focus,
.generic-form-inline .form-select:focus {
  border-color: var(--accent-primary);
  background-color: var(--bg-card);
}

.generic-form-inline .form-label {
  color: var(--text-secondary);
}

.form-input:disabled, .form-select:disabled, .select-custom:disabled {
  background-color: var(--bg-surface) !important;
  border-color: var(--border-color) !important;
  color: var(--text-secondary) !important;
  cursor: not-allowed;
  pointer-events: none;
  opacity: 0.75;
  box-shadow: none !important;
}

.disabled-switch {
  cursor: not-allowed !important;
  opacity: 0.6;
  pointer-events: none;
}

/* Odoo-style layout structural styles */
.form-layout-group {
  margin: 0;
  padding: 8px 12px;
  background-color: var(--bg-surface);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-lg);
}

.group-title {
  grid-column: 1 / -1;
  font-size: 13px;
  font-weight: 700;
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  margin: 0;
  padding-left: 8px;
  border-left: 3px solid var(--accent-primary);
}

.form-layout-separator {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  width: 100%;
}

.separator-title {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-secondary);
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.8px;
}

.form-notebook {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.form-notebook-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 12px;
}

.form-notebook-tab {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
}

.form-notebook-tab:hover {
  color: var(--text-primary);
}

.form-notebook-tab-active {
  color: var(--accent-primary);
  border-bottom-color: var(--accent-primary);
}

.separator-hr {
  flex: 1;
  border: none;
  border-top: 1px solid var(--border-color);
  margin: 0;
}

.form-layout-newline {
  grid-column: 1 / -1;
  height: 0;
  width: 100%;
  margin: 0;
  padding: 0;
}

/* Bulle d'aide (tooltip help) */
.help-tooltip-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
  cursor: help;
}

.help-icon {
  color: rgba(1, 128, 165, 1);
  background: rgba(1, 128, 165, 0.1);
  border-radius: 50%;
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-style: normal;
  font-size: 10px;
  font-weight: bold;
  transition: all var(--transition-fast);
}

.help-icon:hover {
  background: rgba(1, 128, 165, 0.2);
  transform: scale(1.1);
}

.help-tooltip {
  visibility: hidden;
  opacity: 0;
  width: 250px;
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  text-align: left;
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  position: fixed;
  z-index: 9999;
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--border-color);
  font-size: 12px;
  font-weight: normal;
  line-height: 1.5;
  pointer-events: none;
  transition: opacity 0.2s ease, visibility 0.2s ease;
  white-space: normal;
}

/* Tooltip arrow */
.help-tooltip::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 8px;
  margin-left: 0;
  border-width: 5px;
  border-style: solid;
  border-color: var(--bg-secondary) transparent transparent transparent;
}

.help-tooltip-wrapper:hover .help-tooltip {
  visibility: visible;
  opacity: 1;
}

/* Basic styling inside the parsed markdown tooltip */
.help-tooltip strong {
  font-weight: bold;
  color: var(--text-primary);
}

.help-tooltip em {
  font-style: italic;
}

.help-tooltip code {
  background-color: var(--bg-surface);
  color: var(--accent-primary);
  padding: 2px 4px;
  border-radius: var(--radius-md);
  font-family: monospace;
  font-size: 11px;
}

.help-tooltip ul {
  margin: 6px 0 0 0;
  padding-left: 16px;
  list-style-type: disc;
}

.help-tooltip li {
  margin-bottom: 4px;
}

/* Modification groupée */
.multi-edit-banner {
  display: flex;
  gap: 12px;
  background-color: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  border-radius: var(--radius-lg);
  padding: 12px 16px;
  margin-bottom: 15px;
}
.multi-edit-banner-icon {
  font-size: 20px;
  align-self: flex-start;
}
.multi-edit-banner-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.multi-edit-banner-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent-success);
}
.multi-edit-banner-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}
.field-modified-badge {
  background-color: rgba(16, 185, 129, 0.15);
  color: var(--accent-success);
  border: 1px solid rgba(16, 185, 129, 0.3);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: var(--radius-md);
  margin-left: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.field-modified-badge-inline {
  background-color: rgba(16, 185, 129, 0.15);
  color: var(--accent-success);
  border: 1px solid rgba(16, 185, 129, 0.3);
  font-size: 10px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: var(--radius-sm);
}
.form-input-divergent, .form-select-divergent {
  background-color: rgba(156, 163, 175, 0.1) !important;
  border-style: dashed !important;
  border-color: var(--border-color) !important;
  color: var(--text-muted) !important;
}
.form-input-modified, .form-select-modified {
  border-color: var(--accent-success) !important;
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15) !important;
}
.switch-divergent {
  opacity: 0.6;
}
.switch-modified {
  box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);
  border-radius: 34px;
}
.status-divergent {
  color: var(--text-muted) !important;
  font-style: italic;
}
.color-swatch-divergent {
  opacity: 0.6;
  border: 1px dashed var(--text-muted);
}
.color-swatch-modified {
  border: 2px solid var(--accent-success);
}
.color-divergent-text {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin-left: 8px;
}
</style>
