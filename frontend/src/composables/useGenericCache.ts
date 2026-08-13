import { computed, unref, type ComputedRef, type Ref } from 'vue';
import { useQuery, type UseQueryReturnType } from '@tanstack/vue-query';
import { fetchAllGenericItems } from '../services/api';

// Clé canonique partagée par toute l'app pour une collection generic/<resource> :
// ['genericList', resource] sans filtre, ['genericList', resource, filters] avec — exactement la
// même convention que App.vue (genericListQuery, bindGenericListQuery, fkOptionsCache). Un
// composant qui a besoin d'une ressource déjà chargée ailleurs (ex: 'periods' pour la grille EDT)
// partage donc automatiquement le même cache/la même requête réseau, au lieu de la refaire de son
// côté — voir architecture.md §15.T, "unification du cache generic".
export function genericCacheKey(resourceName: string, filters?: Record<string, any> | null) {
  return filters && Object.keys(filters).length > 0
    ? (['genericList', resourceName, filters] as const)
    : (['genericList', resourceName] as const);
}

export function useGenericCache(
  resourceName: string | Ref<string> | ComputedRef<string>,
  filters?: Ref<Record<string, any> | null | undefined> | ComputedRef<Record<string, any> | null | undefined>,
  enabled?: Ref<boolean> | (() => boolean)
): { items: ComputedRef<any[]>; query: UseQueryReturnType<{ total: number; items: any[] }, Error> } {
  const queryKey = computed(() => genericCacheKey(unref(resourceName), filters?.value));
  const query = useQuery({
    queryKey,
    queryFn: () => fetchAllGenericItems(unref(resourceName), undefined, filters?.value || undefined),
    ...(enabled !== undefined ? { enabled } : {}),
  });
  const items = computed(() => query.data.value?.items || []);
  return { items, query };
}
