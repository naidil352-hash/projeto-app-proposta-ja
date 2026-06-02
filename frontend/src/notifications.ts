import { Platform } from "react-native";

// Disable notifications entirely on Expo Go / development
const isDevelopment = __DEV__;

export async function ensureNotificationPermission(): Promise<boolean> {
  if (Platform.OS === "web" || isDevelopment) return false;

  try {
    const Notifications = await import("expo-notifications");

    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });

    const { status } = await Notifications.getPermissionsAsync();

    if (status === "granted") return true;

    const req = await Notifications.requestPermissionsAsync();

    return req.status === "granted";
  } catch (e) {
    console.log("Notifications disabled:", e);
    return false;
  }
}

const SCHEDULE_TAG = "propostaja-followup-3days";

export async function scheduleFollowupReminder() {
  if (Platform.OS === "web" || isDevelopment) return;

  try {
    const Notifications = await import("expo-notifications");

    const all =
      await Notifications.getAllScheduledNotificationsAsync();

    for (const n of all) {
      if (
        n.content?.data &&
        (n.content.data as any).tag === SCHEDULE_TAG
      ) {
        await Notifications.cancelScheduledNotificationAsync(
          n.identifier
        );
      }
    }

    const THREE_DAYS = 60 * 60 * 24 * 3;

    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Hora de fazer follow-up 💬",
        body:
          "Você tem propostas em aberto há 3+ dias. Abra o PROPOSTA JÁ e envie um follow-up no WhatsApp.",
        data: { tag: SCHEDULE_TAG },
      },
      trigger: {
        seconds: THREE_DAYS,
        repeats: true,
      } as any,
    });
  } catch (e) {
    console.log("scheduleFollowupReminder ignored:", e);
  }
}

export async function cancelFollowupReminder() {
  if (Platform.OS === "web" || isDevelopment) return;

  try {
    const Notifications = await import("expo-notifications");

    const all =
      await Notifications.getAllScheduledNotificationsAsync();

    for (const n of all) {
      if (
        n.content?.data &&
        (n.content.data as any).tag === SCHEDULE_TAG
      ) {
        await Notifications.cancelScheduledNotificationAsync(
          n.identifier
        );
      }
    }
  } catch (e) {
    console.log("cancelFollowupReminder ignored:", e);
  }
}