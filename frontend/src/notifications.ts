import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function ensureNotificationPermission(): Promise<boolean> {
  if (Platform.OS === "web") return false;
  const { status } = await Notifications.getPermissionsAsync();
  if (status === "granted") return true;
  const req = await Notifications.requestPermissionsAsync();
  return req.status === "granted";
}

const SCHEDULE_TAG = "propostaja-followup-3days";

export async function scheduleFollowupReminder() {
  if (Platform.OS === "web") return;
  try {
    // Cancel any previously scheduled reminder with our tag
    const all = await Notifications.getAllScheduledNotificationsAsync();
    for (const n of all) {
      if (n.content?.data && (n.content.data as any).tag === SCHEDULE_TAG) {
        await Notifications.cancelScheduledNotificationAsync(n.identifier);
      }
    }
    // Schedule a recurring reminder every 3 days (in seconds)
    const THREE_DAYS = 60 * 60 * 24 * 3;
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Hora de fazer follow-up 💬",
        body: "Você tem propostas em aberto há 3+ dias. Abra o PROPOSTA JÁ e envie um follow-up no WhatsApp.",
        data: { tag: SCHEDULE_TAG },
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.TIME_INTERVAL,
        seconds: THREE_DAYS,
        repeats: true,
      },
    });
  } catch (e) {
    // silently ignore on unsupported environments
  }
}

export async function cancelFollowupReminder() {
  if (Platform.OS === "web") return;
  try {
    const all = await Notifications.getAllScheduledNotificationsAsync();
    for (const n of all) {
      if (n.content?.data && (n.content.data as any).tag === SCHEDULE_TAG) {
        await Notifications.cancelScheduledNotificationAsync(n.identifier);
      }
    }
  } catch {}
}
