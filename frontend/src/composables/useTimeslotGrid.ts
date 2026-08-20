import { computed, Ref } from 'vue';
import { useGenericCache } from './useGenericCache';
import { dayOfWeekSortKey } from '../utils/date';

// Exports de plain functions (pas dans la closure du composable ci-dessous) : appelables
// n'importe où — store Pinia, autre composable... — sans dépendre d'un contexte Vue setup()
// (le composable lui-même appelle useGenericCache -> useQuery, qui échoue hors setup()).

// Timeslot ne porte que minutes_from_midnight (le champ float "hour" a été retiré lors du
// passage à une architecture temporelle en minutes entières, voir 181dec6) — seule source de
// vérité pour cette conversion, à ne plus dupliquer ailleurs.
export function getTimeslotHour(ts: { minutes_from_midnight: number }): number {
  return ts.minutes_from_midnight / 60;
}

// Recherche du timeslot correspondant à un jour/heure donné (tolérance flottante sur l'heure,
// motif dupliqué à l'identique à plusieurs endroits avant cette factorisation).
export function findTimeslotAt<T extends { day_of_week: number; minutes_from_midnight: number }>(
  timeslots: T[],
  day: number,
  hour: number
): T | undefined {
  return timeslots.find(t => t.day_of_week === day && Math.abs(getTimeslotHour(t) - hour) < 0.001);
}

export function useTimeslotGrid(timeslotsRef?: Ref<any[]>) {
  // system_settings partagé (voir useGenericCache, architecture.md §15.T) : plusieurs composants
  // (PreferenceGrid, TimetableGrid, BaseGrid) en avaient chacun leur propre copie, dupliquant le
  // fetch — désormais une seule entrée de cache queryClient, réactive (une invalidation externe,
  // ex: modification du réglage ailleurs, met aussi à jour la grille sans rechargement de page).
  const { items: systemSettings } = useGenericCache('system_settings');
  const currentStandardDuration = computed(() => {
    const durationSetting = systemSettings.value.find((item: any) => item.key === 'STANDARD_TIMESLOT_DURATION');
    return durationSetting ? Number(durationSetting.value) : 30;
  });

  // Repli sur 1 (lundi) tant que le réglage n'a pas été saisi — même convention que
  // time_utils.get_first_day_of_week (backend), seule source de vérité de la rotation.
  const firstDayOfWeek = computed(() => {
    const setting = systemSettings.value.find((item: any) => item.key === 'FIRST_DAY_OF_THE_WEEK');
    return setting ? Number(setting.value) : 1;
  });

  // Récréations (voir BaseGrid.vue, ligne grise en surimpression) — null tant que le réglage
  // n'a pas été saisi (voir wizard_grid_settings.py). L'ACTIVATION de l'affichage (afficher ou
  // non ces lignes) n'est PAS un réglage système : c'est un simple paramètre du composant
  // graphique (BaseGrid.vue::displayBreaks, défaut true), pas une donnée métier.
  const morningBreakStart = computed(() => {
    const setting = systemSettings.value.find((item: any) => item.key === 'HOUR_MORNING_BREAK_START_MINUTES_AFTER_MIDNIGHT');
    return setting && setting.value !== null && setting.value !== '' ? Number(setting.value) : null;
  });
  const afternoonBreakStart = computed(() => {
    const setting = systemSettings.value.find((item: any) => item.key === 'HOUR_AFTERNOON_BREAK_START_MINUTES_AFTER_MIDNIGHT');
    return setting && setting.value !== null && setting.value !== '' ? Number(setting.value) : null;
  });

  const subCellCount = computed(() => {
    return Math.round(60 / currentStandardDuration.value);
  });

  const days = computed(() => {
    if (!timeslotsRef || !timeslotsRef.value || timeslotsRef.value.length === 0) {
      return [];
    }
    const uniqueDaysMap = new Map();
    timeslotsRef.value.forEach(t => {
      if (!uniqueDaysMap.has(t.day_of_week)) {
        uniqueDaysMap.set(t.day_of_week, t.day_of_week_str || ('Jour ' + t.day_of_week));
      }
    });

    // Rotation par FIRST_DAY_OF_THE_WEEK plutôt qu'un tri brut 1=lundi..7=dimanche — seul point de
    // changement pour toute la grille écran (BaseGrid.vue/PreferenceGrid.vue), voir date.ts.
    const sortedDays = Array.from(uniqueDaysMap.entries())
      .sort((a, b) => dayOfWeekSortKey(a[0], firstDayOfWeek.value) - dayOfWeekSortKey(b[0], firstDayOfWeek.value));
    return sortedDays.map(([val, lbl]) => ({ value: val, label: lbl }));
  });

  const hours = computed(() => {
    if (!timeslotsRef || !timeslotsRef.value || timeslotsRef.value.length === 0) {
      return [];
    }
    const uniqueHours = Array.from(new Set(timeslotsRef.value.map(t => Math.floor(getTimeslotHour(t))))).sort((a, b) => a - b);
    if (uniqueHours.length === 0) return [];
    
    const minH = uniqueHours[0];
    const maxH = uniqueHours[uniqueHours.length - 1];
    const fullHours = [];
    for (let h = minH; h <= maxH; h++) {
      fullHours.push(h);
    }
    return fullHours;
  });

  function isTimeslotActive(day: number, hour: number, subIdx: number = 0): boolean {
    if (!timeslotsRef || !timeslotsRef.value || timeslotsRef.value.length === 0) return true;
    const exactHour = hour + subIdx * (currentStandardDuration.value / 60);
    return timeslotsRef.value.some(t => t.day_of_week === day && t.minutes_from_midnight === Math.round(exactHour * 60));
  }

  function getCellKey(day: number, hour: number, subIdx?: number): string {
    if (subIdx !== undefined) {
      return `${day}-${hour}-${subIdx}`;
    }
    return `${day}-${hour}`;
  }

  return {
    days,
    hours,
    currentStandardDuration,
    subCellCount,
    getCellKey,
    isTimeslotActive,
    morningBreakStart,
    afternoonBreakStart,
  };
}
