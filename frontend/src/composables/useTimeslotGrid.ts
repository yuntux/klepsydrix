import { ref, computed, onMounted } from 'vue';

export const days = [
  { value: 1, label: 'Lundi' },
  { value: 2, label: 'Mardi' },
  { value: 3, label: 'Mercredi' },
  { value: 4, label: 'Jeudi' },
  { value: 5, label: 'Vendredi' },
  { value: 6, label: 'Samedi' },
];

export const hours = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17];

export function useTimeslotGrid() {
  const currentStandardDuration = ref(30);

  onMounted(async () => {
    try {
      const res = await fetch('/api/generic/system_settings').then(r => r.json());
      const items = res.items || [];
      const durationSetting = items.find((item: any) => item.key === 'STANDARD_TIMESLOT_DURATION');
      currentStandardDuration.value = durationSetting ? Number(durationSetting.value) : 30;
    } catch (e) {
      console.error("Failed to load standard timeslot duration", e);
    }
  });

  const subCellCount = computed(() => {
    return Math.round(60 / currentStandardDuration.value);
  });

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
  };
}
