import { defineStore } from 'pinia';
import { ref } from 'vue';

// Store partagé pour le système de notifications (boîte rouge/verte en bas à droite, rendue par
// App.vue) — auparavant un état local à App.vue, donc inatteignable depuis un composant qui n'a
// pas App.vue comme parent direct (ex: GenericListModal.vue, monté depuis GenericList.vue).
export interface Notification {
  id: number;
  type: 'success' | 'error' | 'info';
  message: string;
}

export const useNotificationStore = defineStore('notifications', () => {
  const notifications = ref<Notification[]>([]);
  let nextId = 0;

  function removeNotification(id: number) {
    notifications.value = notifications.value.filter(n => n.id !== id);
  }

  function showNotification(type: Notification['type'], message: string) {
    const id = ++nextId;
    notifications.value.push({ id, type, message });
    if (type !== 'error') {
      setTimeout(() => removeNotification(id), 4500);
    }
  }

  return { notifications, showNotification, removeNotification };
});
