/**
 * Browser Notification helpers for the LLM Council.
 *
 * The notification fires only when the chairman's final stage is complete while
 * the user is not actively looking at the tab. We intentionally keep this a
 * thin wrapper around the native Notification API rather than adding a dep.
 */

function isSupported() {
  return typeof window !== 'undefined' && 'Notification' in window;
}

function isUserFocused() {
  if (typeof document === 'undefined') return false;
  return document.visibilityState === 'visible' && document.hasFocus();
}

let navigateCallback = null;

/**
 * Allows the React Router layer to register a navigation function so that
 * clicking a notification uses an in-app route change instead of a full page
 * reload. Pass `null` to unregister (e.g. on app unmount).
 */
export function setNotificationNavigationCallback(cb) {
  navigateCallback = cb ?? null;
}

/**
 * Request notification permission from the browser.
 * Safe to call repeatedly — it only prompts when permission is "default".
 */
export async function ensureNotificationPermission() {
  if (!isSupported()) return 'unsupported';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  try {
    const result = await Notification.requestPermission();
    return result;
  } catch (err) {
    console.error('Failed to request notification permission:', err);
    return 'denied';
  }
}

const VERDICT_ANCHOR = '#council-verdict';

/**
 * Show a notification that the chairman has finished the final answer.
 *
 * Clicking the notification focuses the tab, navigates to the conversation,
 * and scrolls to the verdict section ( anchored at `#council-verdict` ).
 *
 * @param {Object} options
 * @param {string} [options.conversationId]
 * @param {string} [options.conversationTitle]
 * @param {boolean} [options.hasError] chairman stage returned an error object
 */
export function notifyChairmanDone({
  conversationId,
  conversationTitle,
  hasError = false,
} = {}) {
  if (!isSupported()) return;
  if (Notification.permission !== 'granted') return;
  if (isUserFocused()) return;

  const title = hasError
    ? 'The Council hit an issue'
    : 'The Council has spoken';

  const body = hasError
    ? 'The chairman stage failed. Open the tab to see what happened.'
    : conversationTitle
      ? `${conversationTitle}: the chairman finished the final answer.`
      : 'The chairman finished the final answer.';

  try {
    const notification = new Notification(title, {
      body,
      icon: '/council.svg',
      badge: '/council.svg',
    });

    notification.onclick = () => {
      if (typeof window !== 'undefined') {
        window.focus();
        if (conversationId) {
          if (navigateCallback) {
            navigateCallback(conversationId);
          } else {
            window.location.href = `/c/${conversationId}${VERDICT_ANCHOR}`;
          }
        }
      }
      notification.close();
    };
  } catch (err) {
    console.error('Failed to show chairman notification:', err);
  }
}
