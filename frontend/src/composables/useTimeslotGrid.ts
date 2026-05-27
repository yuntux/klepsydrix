import { ref, computed, onMounted, Ref } from 'vue';

export function useTimeslotGrid(timeslotsRef?: Ref<any[]>) {
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
    
    const sortedDays = Array.from(uniqueDaysMap.entries()).sort((a, b) => a[0] - b[0]);
    return sortedDays.map(([val, lbl]) => ({ value: val, label: lbl }));
  });

  const hours = computed(() => {
    if (!timeslotsRef || !timeslotsRef.value || timeslotsRef.value.length === 0) {
      return [];
    }
    const uniqueHours = Array.from(new Set(timeslotsRef.value.map(t => Math.floor(t.hour)))).sort((a, b) => a - b);
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
    return timeslotsRef.value.some(t => t.day_of_week === day && Math.abs(t.hour - exactHour) < 0.001);
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
  };
}
