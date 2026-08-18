import { ref, watch, onUnmounted, nextTick, type Ref } from 'vue';
import { computePosition, offset, flip, shift, autoUpdate } from '@floating-ui/dom';

/**
 * Positionnement d'un dropdown en `position: fixed`, calé sur son ancre (`anchorRef`) via
 * Floating UI (successeur de Popper.js, ~5 Ko) — utilisé conjointement à `<Teleport to="body">`
 * par SearchableSelect.vue et SearchableMultiSelect.vue (voir ces fichiers). Sans téléportation +
 * positionnement viewport, un dropdown en `position: absolute` classique reste imbriqué dans le
 * DOM de son conteneur : dès que ce conteneur vit dans une zone scrollable qui ne fait pas
 * elle-même toute la hauteur nécessaire (ex: GenericWizard.vue dans une BaseModal), son overflow
 * s'ajoute à celui de l'ancêtre scrollable au lieu de flotter par-dessus — un ascenseur apparaît
 * là où on attendait un simple menu déroulant.
 *
 * Delegated à Floating UI plutôt que réimplémenté à la main (voir historique architecture.md
 * §15.K / ideas_for_later.md) : `flip` retourne le dropdown au-dessus de l'ancre s'il n'y a pas
 * assez de place en dessous, `shift` le recale pour ne jamais déborder du viewport horizontalement
 * — deux cas que la première version (hand-rolled) ne gérait pas. `autoUpdate` (scroll/resize/
 * mutation de layout) remplace les listeners scroll/resize posés à la main.
 */
export function useFloatingDropdown(anchorRef: Ref<HTMLElement | null>, floatingRef: Ref<HTMLElement | null>, isOpen: Ref<boolean>) {
  const dropdownStyle = ref<Record<string, string>>({ position: 'fixed', top: '0px', left: '0px' });
  let stopAutoUpdate: (() => void) | null = null;

  async function updatePosition() {
    const anchor = anchorRef.value;
    const floating = floatingRef.value;
    if (!anchor || !floating) return;
    const { x, y, strategy } = await computePosition(anchor, floating, {
      strategy: 'fixed',
      placement: 'bottom-start',
      middleware: [offset(4), flip({ fallbackPlacements: ['top-start'] }), shift({ padding: 8 })],
    });
    dropdownStyle.value = {
      position: strategy,
      top: `${y}px`,
      left: `${x}px`,
      width: `${anchor.getBoundingClientRect().width}px`,
    };
  }

  watch(isOpen, async (open) => {
    if (!open) {
      stopAutoUpdate?.();
      stopAutoUpdate = null;
      return;
    }
    // nextTick : le dropdown (v-if) ne vient d'être monté que dans le rendu qui suit isOpen=true —
    // floatingRef.value est encore null au moment où ce watcher se déclenche.
    await nextTick();
    const anchor = anchorRef.value;
    const floating = floatingRef.value;
    if (!anchor || !floating) return;
    stopAutoUpdate = autoUpdate(anchor, floating, updatePosition);
  });

  onUnmounted(() => stopAutoUpdate?.());

  return { dropdownStyle };
}
