import { useCallback, useRef } from 'react';

/**
 * Scroll behavior for the pinned tab strips in Stage I and Stage II.
 *
 * The strip itself is pure CSS (`position: sticky`, see StageTabs.css); this
 * hook only decides what a tab switch does to the scroll position:
 *
 * - Strip pinned (the reader is somewhere inside a long answer): jump so the
 *   newly selected tab's content starts just below the strip, instead of
 *   leaving them stranded mid-way through the new answer.
 * - Strip not pinned (still at its natural spot): leave the scroll alone.
 *
 * "Pinned" is detected geometrically: in normal flow the list sits flush at
 * the top of `Tabs.Root`; sticky positioning pushes it down from there, so a
 * positive offset means it is stuck.
 *
 * The jump is instant (`behavior: 'auto'`). A smooth scroll would animate
 * upward through the content of the tab that was just selected, which reads
 * as noise. The scroll target is `Tabs.Root`, whose `scroll-margin-top`
 * (`--stage-nav-offset`) parks the strip right under the section nav.
 *
 * `onUserReading` (ChatInterface's reading-intent marker) is still called on
 * every switch, before the scroll, so live-run heartbeat auto-follow doesn't
 * cancel the jump.
 */
export default function useStickyTabs(onUserReading) {
  const rootRef = useRef(null); // Tabs.Root
  const listRef = useRef(null); // Tabs.List

  const onValueChange = useCallback(
    (value) => {
      onUserReading?.(value);

      const root = rootRef.current;
      const list = listRef.current;
      if (!root || !list) return;

      const stuck =
        list.getBoundingClientRect().top - root.getBoundingClientRect().top > 1;
      if (stuck) root.scrollIntoView({ block: 'start', behavior: 'auto' });
    },
    [onUserReading],
  );

  return { rootRef, listRef, onValueChange };
}
