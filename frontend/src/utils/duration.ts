// Pendant frontend de backend/app/core/time_utils.py (minutes_to_hours / get_duration_options) —
// fonctions pures, sans dépendance Vue, pour que le type de champ générique "duration"
// (GenericList.vue/GenericForm.vue) affiche et édite une durée en minutes sans jamais faire de
// requête réseau par champ (le pas de créneau, seule donnée externe nécessaire, est lu une fois
// via useTimeslotGrid().currentStandardDuration, voir DurationInput.vue).

// Même borne que get_duration_options côté backend (8h) — au-delà, un champ n'a pas vocation à
// être un simple multiple du créneau standard édité via liste déroulante (voir architecture.md).
export const MAX_DURATION_MINUTES = 480;

// Mirroir exact de minutes_to_hours (backend) : jamais de padding sur l'heure, minutes omises
// quand la durée tombe sur un nombre exact d'heures. Ex: 90 -> "1h30", 60 -> "1h".
export function formatDurationMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h}h` : `${h}h${String(m).padStart(2, '0')}`;
}

// Mirroir exact de get_duration_options (backend) : options par pas de `stepMinutes` jusqu'à
// MAX_DURATION_MINUTES, libellées "X min" (<60min) ou au format Xh/XhYY (>=60min, via
// formatDurationMinutes). includeZero insère {value:0, label:"Aucune"} en tête — pour les champs
// où 0 est une valeur valide signifiant "modalité non utilisée" (voir ColumnConfig/FormField
// durationIncludeZero).
export function getDurationOptions(stepMinutes: number, includeZero = false): Array<{ value: number; label: string }> {
  const numSlots = Math.floor(MAX_DURATION_MINUTES / stepMinutes);
  const options = Array.from({ length: numSlots }, (_, i) => {
    const value = stepMinutes * (i + 1);
    const label = value >= 60 ? formatDurationMinutes(value) : `${value} min`;
    return { value, label };
  });
  if (includeZero) options.unshift({ value: 0, label: 'Aucune' });
  return options;
}
