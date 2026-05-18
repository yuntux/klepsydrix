<template>
  <div :class="inline ? 'inline-form-container' : 'modal-overlay'">
    <div :class="inline ? 'generic-form-inline' : 'generic-form-modal glass-morphism'">
      <div class="form-header">
        <h3 class="form-title">{{ title }}</h3>
        <button v-if="!inline" class="btn-close" @click="$emit('cancel')">×</button>
      </div>

      <form @submit.prevent="handleSubmit" class="form-body">
        <FormLayoutGrid
          :elements="layoutTree"
          :localModel="localModel"
          :isEditableForm="isEditableForm"
          :inline="inline"
        />

        <div class="form-actions">
          <button v-if="localModel && localModel.id" type="button" class="btn btn-danger btn-delete" @click="handleDelete">
            Supprimer
          </button>
          <button v-if="!inline" type="button" class="btn btn-secondary" @click="$emit('cancel')">
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

interface FormField {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'date' | 'select' | 'color';
  required?: boolean;
  placeholder?: string;
  min?: number;
  max?: number;
  step?: string;
  fullWidth?: boolean;
  options?: Array<{ value: any; label: string }>;
}

interface LayoutElement {
  type: 'field' | 'group' | 'separator' | 'newline';
  key?: string;
  string?: string;
  col?: number;
  children?: LayoutElement[];
  readOnly?: boolean;
  required?: boolean;
  overrideLabel?: string;
  label?: string;
  disabled?: boolean;
  originalField?: FormField;
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
        required: original.required,
        disabled: false,
        originalField: original
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
        required: elem.required === true,
        disabled: elem.readOnly === true,
        originalField: original
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
        required: elem.required === true,
        disabled: elem.readOnly === true,
        originalField: original
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
    required: f.required,
    disabled: false,
    originalField: f
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
    }
  },
  setup(props) {
    return () => {
      // Si inline : 150px 1fr
      // Si non inline : 150px 1fr 150px 1fr
      const gridTemplate = props.inline
        ? '150px 1fr'
        : '150px 1fr 150px 1fr';

      return h('div', {
        class: 'fields-layout-container',
        style: props.isNested ? {
          display: 'contents'
        } : {
          display: 'grid',
          gridTemplateColumns: gridTemplate,
          gap: '16px',
          alignItems: 'center',
          width: '100%'
        }
      },
        props.elements.flatMap(elem => {
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
            const cols = props.inline ? 1 : (elem.col || 2);
            const groupGridTemplate = cols === 1 ? '150px 1fr' : '150px 1fr 150px 1fr';
            return [
              h('div', {
                class: 'form-layout-group',
                style: {
                  display: 'grid',
                  gridTemplateColumns: groupGridTemplate,
                  gap: '16px',
                  gridColumn: '1 / -1',
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
                    margin: '0 0 12px 0',
                    paddingLeft: '8px',
                    borderLeft: '3px solid var(--accent-primary)'
                  }
                }, elem.string) : null,
                h(FormLayoutGrid, {
                  elements: elem.children || [],
                  localModel: props.localModel,
                  isEditableForm: props.isEditableForm,
                  inline: props.inline,
                  isNested: true
                })
              ])
            ];
          }

          if (elem.type === 'field' && elem.originalField) {
            const field = elem.originalField;
            const key = elem.key!;
            const required = elem.required === true;
            const disabled = props.isEditableForm === false || elem.disabled === true;
            const label = elem.label || field.label;

            const isFull = field.fullWidth === true;
            const inputStyle = {
              gridColumn: (isFull && !props.inline) ? 'span 3' : 'auto'
            };

            let inputElement: any = null;

            if (field.type === 'text') {
              inputElement = h('input', {
                type: 'text',
                class: 'form-input',
                style: inputStyle,
                value: props.localModel[key] || '',
                required: required,
                disabled: disabled,
                placeholder: field.placeholder || '',
                onInput: (e: Event) => {
                  props.localModel[key] = (e.target as HTMLInputElement).value;
                }
              });
            } else if (field.type === 'number') {
              inputElement = h('input', {
                type: 'number',
                class: 'form-input',
                style: inputStyle,
                value: props.localModel[key] !== undefined && props.localModel[key] !== null ? props.localModel[key] : '',
                required: required,
                disabled: disabled,
                min: field.min,
                max: field.max,
                step: field.step || '1',
                onInput: (e: Event) => {
                  const val = (e.target as HTMLInputElement).value;
                  props.localModel[key] = val !== '' ? Number(val) : null;
                }
              });
            } else if (field.type === 'date') {
              inputElement = h('input', {
                type: 'date',
                class: 'form-input',
                style: inputStyle,
                value: props.localModel[key] || '',
                required: required,
                disabled: disabled,
                onInput: (e: Event) => {
                  props.localModel[key] = (e.target as HTMLInputElement).value;
                }
              });
            } else if (field.type === 'boolean') {
              inputElement = h('div', {
                class: 'toggle-wrapper',
                style: inputStyle
              }, [
                h('label', { class: ['switch', disabled ? 'disabled-switch' : ''] }, [
                  h('input', {
                    type: 'checkbox',
                    checked: !!props.localModel[key],
                    disabled: disabled,
                    onChange: (e: Event) => {
                      props.localModel[key] = (e.target as HTMLInputElement).checked;
                    }
                  }),
                  h('span', { class: 'slider round' })
                ]),
                h('span', { class: 'toggle-status' }, props.localModel[key] ? 'Oui' : 'Non')
              ]);
            } else if (field.type === 'select') {
              inputElement = h('select', {
                class: 'select-custom form-select',
                style: inputStyle,
                value: props.localModel[key] !== undefined && props.localModel[key] !== null ? props.localModel[key] : '',
                required: required,
                disabled: disabled,
                onChange: (e: Event) => {
                  const val = (e.target as HTMLSelectElement).value;
                  props.localModel[key] = val === '' ? null : Number(val);
                }
              }, [
                h('option', { value: '' }, '-- Choisir --'),
                ...(field.options || []).map(opt =>
                  h('option', { value: opt.value }, opt.label)
                )
              ]);
            } else if (field.type === 'color') {
              inputElement = h('div', {
                class: ['form-color-swatch-wrapper', disabled ? 'readonly-swatch' : ''],
                style: inputStyle
              }, [
                h(ColorSwatchPicker, {
                  modelValue: props.localModel[key] || '#3B82F6',
                  onChange: (val: string) => {
                    props.localModel[key] = val;
                  }
                })
              ]);
            }

            const labelElement = h('label', {
              class: 'form-label',
              for: key,
              style: {
                gridColumn: 'auto'
              }
            }, [
              label,
              required ? h('span', { class: 'required-indicator' }, ' *') : null
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

// Watch props.modelValue pour mettre à jour la copie locale
watch(() => props.modelValue, (newVal) => {
  const cleanNewVal = newVal ? { ...newVal } : {};
  if (JSON.stringify(cleanNewVal) === JSON.stringify(localModel.value)) return;
  
  localModel.value = cleanNewVal;
  
  // Initialiser les champs booléens et couleur par défaut
  props.fields.forEach(field => {
    if (field.type === 'boolean' && localModel.value[field.key] === undefined) {
      localModel.value[field.key] = false;
    }
    if (field.type === 'color' && !localModel.value[field.key]) {
      localModel.value[field.key] = '#3498DB'; // couleur par défaut premium
    }
    if (field.type === 'select' && localModel.value[field.key] === undefined) {
      localModel.value[field.key] = null;
    }
  });
}, { immediate: true, deep: true });

// Synchroniser les saisies locales en temps réel avec le parent pour forcer la réactivité du bouton d'ajout
watch(localModel, (newVal) => {
  if (JSON.stringify(newVal) === JSON.stringify(props.modelValue)) return;
  emit('update:modelValue', { ...newVal });
}, { deep: true });

function handleSubmit() {
  emit('update:modelValue', localModel.value);
  emit('submit', localModel.value);
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
  border-radius: 6px;
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
  padding: 24px;
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
  border-radius: 4px;
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
  background-color: #FFFFFF;
  border-left: 1px solid #E2E8F0;
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
  background-color: #F8FAFC;
  border-bottom: 1px solid #E2E8F0;
  padding: 14px 20px;
}

.generic-form-inline .form-title {
  color: #1E293B;
  font-size: 14px;
}

.generic-form-inline .form-body {
  padding: 20px;
  background-color: #FFFFFF;
  overflow-y: auto;
  flex: 1;
}

.generic-form-inline .form-input,
.generic-form-inline .form-select {
  background-color: #F8FAFC;
  border: 1px solid #CBD5E1;
  color: #1E293B;
}

.generic-form-inline .form-input:focus,
.generic-form-inline .form-select:focus {
  border-color: #6366F1;
  background-color: #FFFFFF;
}

.generic-form-inline .form-label {
  color: #475569;
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
  border-radius: 6px;
}

.group-title {
  grid-column: 1 / -1;
  font-size: 13px;
  font-weight: 700;
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing: 0.7px;
  margin: 0 0 12px 0;
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
</style>
