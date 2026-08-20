// Pendant frontend de backend/app/core/date_utils.py — fonctions pures, sans dépendance Vue.

export const DAY_NAMES: Record<number, string> = {
  1: 'Lundi', 2: 'Mardi', 3: 'Mercredi', 4: 'Jeudi', 5: 'Vendredi', 6: 'Samedi', 7: 'Dimanche',
};

// Mirroir exact de day_of_week_label (backend). Convention day_of_week: 1=lundi ... 7=dimanche.
export function dayOfWeekLabel(dayOfWeek: number): string {
  return DAY_NAMES[dayOfWeek] || `Jour ${dayOfWeek}`;
}

// Mirroir exact de day_of_week_sort_key (backend) : position 0-based d'un jour dans une semaine
// d'affichage qui commence à `firstDayOfWeek` — voir useTimeslotGrid.ts (seul consommateur actuel).
export function dayOfWeekSortKey(dayOfWeek: number, firstDayOfWeek: number): number {
  return ((dayOfWeek - firstDayOfWeek) % 7 + 7) % 7;
}

// "480" -> "08h00" — même convention d'affichage que Timeslot.display_name (backend), pour les
// listes déroulantes d'horaires (voir TimeslotPickerField.vue) et les champs "heure" natifs
// (ClockTimeField.vue).
export function formatClockTime(minutesFromMidnight: number | null | undefined): string {
  if (minutesFromMidnight === null || minutesFromMidnight === undefined) return '';
  const h = Math.floor(minutesFromMidnight / 60);
  const m = minutesFromMidnight % 60;
  return `${String(h).padStart(2, '0')}h${String(m).padStart(2, '0')}`;
}

// "08:00" (valeur native d'un <input type="time">) <-> 480. Pendant HTML5 de formatClockTime.
export function minutesToTimeInputValue(minutesFromMidnight: number | null | undefined): string {
  if (minutesFromMidnight === null || minutesFromMidnight === undefined) return '';
  const h = Math.floor(minutesFromMidnight / 60);
  const m = minutesFromMidnight % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function timeInputValueToMinutes(value: string): number | null {
  if (!value) return null;
  const [h, m] = value.split(':').map(Number);
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  return h * 60 + m;
}
