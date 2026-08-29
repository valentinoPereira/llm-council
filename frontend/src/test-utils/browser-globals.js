/**
 * Minimal browser globals stub for testing `notifications.js` in Node.
 *
 * These fakes are intentionally small — they only model the surface area used
 * by the notification helpers.
 */

export function createFakeNotification() {
  let lastInstance = null;

  class FakeNotification {
    static permission = 'default';

    static requestPermissionResult = 'granted';

    static async requestPermission() {
      return FakeNotification.requestPermissionResult;
    }

    constructor(title, options = {}) {
      this.title = title;
      this.body = options.body;
      this.icon = options.icon;
      this.badge = options.badge;
      this.closed = false;
      lastInstance = this;
    }

    close() {
      this.closed = true;
    }

    onclick = null;
  }

  return {
    FakeNotification,
    getLastNotification: () => lastInstance,
    resetLastNotification: () => {
      lastInstance = null;
    },
  };
}

export function installBrowserGlobals() {
  const { FakeNotification, getLastNotification, resetLastNotification } =
    createFakeNotification();

  const focusCalls = [];
  const navigations = [];

  const fakeDocument = {
    visibilityState: 'visible',
    _focused: true,
    hasFocus() {
      return fakeDocument._focused;
    },
  };

  const fakeWindow = {
    focus() {
      focusCalls.push(true);
    },
    location: { href: '' },
    document: fakeDocument,
    Notification: FakeNotification,
  };

  globalThis.Notification = FakeNotification;
  globalThis.document = fakeDocument;
  globalThis.window = fakeWindow;

  return {
    FakeNotification,
    getLastNotification,
    resetLastNotification,
    focusCalls,
    navigations,
    fakeDocument,
    fakeWindow,
  };
}

export function uninstallBrowserGlobals() {
  delete globalThis.Notification;
  delete globalThis.document;
  delete globalThis.window;
}
