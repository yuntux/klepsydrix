import { computed, unref, type ComputedRef, type Ref } from 'vue';
import { useQuery, type UseQueryReturnType, type QueryKey } from '@tanstack/vue-query';
import { fetchAllGenericItems } from '../services/api';

// Clé canonique partagée par toute l'app pour une collection generic/<resource> :
// ['genericList', resource] sans filtre, ['genericList', resource, filters] avec — exactement la
// même convention que App.vue (genericListQuery, bindGenericListQuery, fkOptionsCache). Un
// composant qui a besoin d'une ressource déjà chargée ailleurs (ex: 'periods' pour la grille EDT)
// partage donc automatiquement le même cache/la même requête réseau, au lieu de la refaire de son
// côté — voir architecture.md §15.T, "unification du cache generic".
//
// Annotation de retour explicite (QueryKey, le type canonique de TanStack, readonly unknown[]) —
// sans elle, TS infère une UNION de deux tuples de longueurs différentes (2 vs 3 éléments), que
// useQuery ne sait pas résoudre (No overload matches this call). Ne change rien à la forme
// réellement renvoyée à l'exécution (toujours 2 ou 3 éléments selon le cas) : App.vue s'appuie
// explicitement sur cette longueur exacte (voir invalidateFkCache, `key.length !== 2`) pour
// distinguer une clé "sans filtre" d'une clé "avec filtre" — ne jamais l'uniformiser à 3 éléments.
export function genericCacheKey(resourceName: string, filters?: Record<string, any> | null): QueryKey {
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
