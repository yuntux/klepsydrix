<template>
  <div :class="inline ? 'inline-form-container' : 'modal-overlay'">
    <div :class="inline ? 'generic-form-inline' : 'generic-form-modal glass-morphism'">
      <div class="form-header">
        <h3 class="form-title">{{ isMultiEdit ? 'Modification groupée' : title }}</h3>
        <button v-if="!inline" class="btn-close" @click="handleCancel">×</button>
      </div>

      <form @submit.prevent="handleSubmit" class="form-body">
        <div v-if="isMultiEdit" class="multi-edit-banner">
          <span class="multi-edit-banner-icon">✏️</span>
          <div class="multi-edit-banner-content">
            <div class="multi-edit-banner-title">Modification groupée ({{ selectedRecords.length }} éléments)</div>
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
          <button v-if="localModel && localModel.id && !isMultiEdit" type="button" class="btn btn-danger btn-delete" @click="handleDelete">
            Supprimer
          </button>
          <button type="button" class="btn btn-secondary" @click="handleCancel">
            Annuler
          </button>
          <button v-if="isEditableForm" type="submit" class="btn btn-primary">
            Enregistrer
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, defineComponent, h } from 'vue';
import ColorSwatchPicker from './ColorSwatchPicker.vue';
import SearchableSelect from './SearchableSelect.vue';
import SearchableMultiSelect from './SearchableMultiSelect.vue';
import Many2ManyOrderedList from './widgets/Many2ManyOrderedList.vue';


interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'color' | 'multiselect';
  required?: boolean;
  requiredExpr?: string;
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
}
interface LayoutElement {
  type: 'field' | 'group' | 'separator' | 'newline';
  key?: string;
  string?: string;
  col?: number;
  span?: number;
  children?: LayoutElement[];
  readOnly?: boolean;
  readOnlyExpr?: string;
  requiredExpr?: string;
  invisibleExpr?: string;
  widget?: string;
  widgetParams?: any;
  overrideLabel?: string;
  label?: string;
  disabled?: boolean;
  originalField?: FormField;
  help?: string;
}
function renderMarkdown(md: string | undefined): string {
  if (!md) return '';
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
  
  return processedLines.join('\n');
}

interface FormConfig {
  editableForm?: boolean;
  fields?: any[];
}

const props = defineProps<{
  title: string;
  fields: FormField[];
  modelValue: Record<string, any>;
  inline?: boolean;
  formConfig?: FormConfig;
  selectedRecords?: any[];
  resourceKey?: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, any>): void;
  (e: 'submit', value: Record<string, any>): void;
  (e: 'cancel'): void;
  (e: 'delete', value: Record<string, any>): void;
}>();



const isEditableForm = computed(() => {
  return props.formConfig?.editableForm !== false;
});

function parseLayoutElement(elem: any): LayoutElement | null {
  if (!elem) return null;
  
  if (typeof elem === 'string') {
    const original = props.fields.find(f => f.key === elem);
    if (original) {
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
    if (original) {
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
        help: elem.help || original.help
      };
    }
  }

  if (elem.type === 'field') {
    const original = props.fields.find(f => f.key === elem.key);
    if (original) {
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
        help: elem.help || original.help
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

  return null;
}

const layoutTree = computed<LayoutElement[]>(() => {
  if (props.formConfig?.fields && props.formConfig.fields.length > 0) {
    const parsed: LayoutElement[] = [];
    props.formConfig.fields.forEach((item: any) => {
      const parsedItem = parseLayoutElement(item);
      if (parsedItem) parsed.push(parsedItem);
    });
    return parsed;
  }

  // Fallback par défaut : tous les champs dans un layout plat
  return props.fields.map(f => ({
    type: 'field',
    key: f.key,
    label: f.label,
    required: f.required === true,
    requiredExpr: f.requiredExpr,
    disabled: false,
    readOnlyExpr: f.readOnlyExpr,
    invisibleExpr: f.invisibleExpr,
    originalField: f,
    help: f.help
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

            if (elem.widget === 'many2many_ordered_list') {
              inputElement = h(Many2ManyOrderedList, {
                modelValue: Array.isArray(gridProps.localModel[key]) ? gridProps.localModel[key] : (gridProps.localModel[key] ? [gridProps.localModel[key]] : []),
                field: field,
                widgetParams: elem.widgetParams,
                disabled: disabled,
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
              const options = field.options || [];
              inputElement = h(SearchableSelect, {
                modelValue: gridProps.localModel[key] !== undefined && gridProps.localModel[key] !== null ? gridProps.localModel[key] : null,
                options: options,
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
                h('label', { class: ['switch', disabled ? 'disabled-switch' : '', isDivergent(key) && !isModified(key) ? 'switch-divergent' : '', isModified(key) ? 'switch-modified' : ''] }, [
                  h('input', {
                    type: 'checkbox',
                    checked: !!gridProps.localModel[key],
                    disabled: disabled,
                    onChange: (e: Event) => {
                      gridProps.localModel[key] = (e.target as HTMLInputElement).checked;
                    }
                  }),
                  h('span', { class: 'slider round' })
                ]),
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
                h('option', { value: '' }, isDivergent(key) && !isModified(key) ? '-- Divergent (Modifier) --' : '-- Choisir --'),
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
                elem.help ? h('span', {
                  class: 'help-tooltip-wrapper',
                  onClick: (e: Event) => e.stopPropagation()
                }, [
                  h('span', { class: 'help-icon' }, '?'),
                  h('span', {
                    class: 'help-tooltip',
                    innerHTML: renderMarkdown(elem.help)
                  })
                ]) : null
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

// Copie locale réactive pour éviter de modifier directement le modèle parent avant soumission
const localModel = ref<Record<string, any>>({});
const initialModelValue = ref<Record<string, any>>({});

const isMultiEdit = computed(() => {
  return props.selectedRecords && props.selectedRecords.length > 1;
});

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
        const response = await fetch(`/api/generic/${props.resourceKey}/onchange`, {
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
  if (isMultiEdit.value) {
    const submitPayload: Record<string, any> = {};
    props.fields.forEach(field => {
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
    emit('submit', localModel.value);
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

.form-input, .form-select {
  width: 100%;
  box-sizing: border-box;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  font-family: var(--font-sans);
  transition: all var(--transition-fast);
}

.form-input:focus, .form-select:focus {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
}

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

.switch {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--bg-secondary);
  border: 1px solid var(--border-color);
  transition: .3s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: var(--text-secondary);
  transition: .3s;
}

input:checked + .slider {
  background-color: rgba(99, 102, 241, 0.2);
  border-color: var(--accent-primary);
}

input:checked + .slider:before {
  transform: translateX(24px);
  background-color: var(--accent-primary);
}

.slider.round {
  border-radius: 34px;
}

.slider.round:before {
  border-radius: 50%;
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
  margin-top: 10px;
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
  position: absolute;
  z-index: 1000;
  bottom: 125%; /* Position the tooltip above the text */
  left: 50%;
  transform: translateX(-50%);
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
  top: 100%; /* At the bottom of the tooltip */
  left: 50%;
  margin-left: -5px;
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
