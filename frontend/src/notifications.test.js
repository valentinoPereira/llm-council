import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  installBrowserGlobals,
  uninstallBrowserGlobals,
} from './test-utils/browser-globals.js';

let notifications;
let globals;

describe('notifications.js', () => {
  beforeEach(async () => {
    globals = installBrowserGlobals();
    notifications = await import('./notifications.js');
  });

  afterEach(() => {
    notifications.setNotificationNavigationCallback(null);
    globals.resetLastNotification();
    uninstallBrowserGlobals();
  });

  describe('ensureNotificationPermission', () => {
    it('returns unsupported when Notification is not available', async () => {
      uninstallBrowserGlobals();
      const result = await notifications.ensureNotificationPermission();
      assert.equal(result, 'unsupported');
    });

    it('returns granted when permission is already granted', async () => {
      globals.FakeNotification.permission = 'granted';
      const result = await notifications.ensureNotificationPermission();
      assert.equal(result, 'granted');
    });

    it('returns denied when permission is already denied', async () => {
      globals.FakeNotification.permission = 'denied';
      const result = await notifications.ensureNotificationPermission();
      assert.equal(result, 'denied');
    });

    it('requests permission when status is default', async () => {
      globals.FakeNotification.permission = 'default';
      globals.FakeNotification.requestPermissionResult = 'granted';
      const result = await notifications.ensureNotificationPermission();
      assert.equal(result, 'granted');
    });
  });

  describe('notifyChairmanDone', () => {
    it('does nothing if permission is denied', () => {
      globals.FakeNotification.permission = 'denied';
      notifications.notifyChairmanDone({ conversationId: 'abc' });
      assert.equal(globals.getLastNotification(), null);
    });

    it('does nothing if the user is focused', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = true;
      globals.fakeDocument.visibilityState = 'visible';
      notifications.notifyChairmanDone({ conversationId: 'abc' });
      assert.equal(globals.getLastNotification(), null);
    });

    it('shows a notification when the stage completes while the tab is hidden', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = false;
      globals.fakeDocument.visibilityState = 'hidden';

      notifications.notifyChairmanDone({
        conversationId: 'conv-123',
        conversationTitle: 'My Question',
      });

      const notification = globals.getLastNotification();
      assert.ok(notification);
      assert.equal(notification.title, 'The Council has spoken');
      assert.equal(
        notification.body,
        'My Question: the chairman finished the final answer.'
      );
      assert.equal(notification.icon, '/council.svg');
    });

    it('uses the error title and body when hasError is true', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = false;
      globals.fakeDocument.visibilityState = 'hidden';

      notifications.notifyChairmanDone({ hasError: true });

      const notification = globals.getLastNotification();
      assert.equal(notification.title, 'The Council hit an issue');
      assert.equal(
        notification.body,
        'The chairman stage failed. Open the tab to see what happened.'
      );
    });

    it('falls back to a generic body when no title is provided', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = false;
      globals.fakeDocument.visibilityState = 'hidden';

      notifications.notifyChairmanDone({});

      const notification = globals.getLastNotification();
      assert.equal(
        notification.body,
        'The chairman finished the final answer.'
      );
    });

    it('calls the registered navigation callback on click', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = false;
      globals.fakeDocument.visibilityState = 'hidden';

      const navArgs = [];
      notifications.setNotificationNavigationCallback((id) =>
        navArgs.push(id)
      );

      notifications.notifyChairmanDone({ conversationId: 'nav-target' });
      const notification = globals.getLastNotification();
      notification.onclick();

      assert.deepEqual(navArgs, ['nav-target']);
      assert.equal(globals.fakeWindow.location.href, '');
      assert.equal(notification.closed, true);
      assert.equal(globals.focusCalls.length, 1);
    });

    it('falls back to window.location.href when no callback is registered', () => {
      globals.FakeNotification.permission = 'granted';
      globals.fakeDocument._focused = false;
      globals.fakeDocument.visibilityState = 'hidden';

      notifications.notifyChairmanDone({ conversationId: 'fallback-target' });
      const notification = globals.getLastNotification();
      notification.onclick();

      assert.equal(
        globals.fakeWindow.location.href,
        '/c/fallback-target#council-verdict'
      );
    });
  });
});
