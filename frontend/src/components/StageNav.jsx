import { useEffect, useRef, useState } from 'react';
import './StageNav.css';

/**
 * Sticky section jump-nav, rendered above the stage sections of an
 * assistant message. Lets the reader hop between the question and each
 * stage (I / II / III) without scrolling through the full transcript.
 *
 * Active section is tracked with an IntersectionObserver (scrollspy):
 * the topmost section crossing the upper band of the scrollport is
 * considered current and its button highlighted.
 *
 * `onJump` is called on every nav click. ChatInterface passes its reading-
 * intent marker there: without it, the auto-scroll "pin to bottom" that runs
 * on each server heartbeat during a live run would cancel the smooth
 * scrollIntoView midway, leaving the section out of the spy band (so it never
 * highlights) until the user scrolls manually.
 *
 * During a programmatic jump the spy is suppressed: the observer fires
 * transition entries for sections the scroll merely passes through (e.g.
 * Peer Review on the way to Verdict), making the highlight bounce
 * Verdict → Peer Review → Verdict. The clicked section stays lit until the
 * scroll finishes (`scrollend`, with a timer fallback for browsers that
 * never fire it, or when the jump is already a no-op at the target), then
 * the observer resumes ownership.
 */
export default function StageNav({ sections, onJump }) {
  const [activeId, setActiveId] = useState(null);
  // Sections that arrived after this nav mounted (the run is live and a
  // later stage just finished) — they get the pulse + dot until seen.
  const [newIds, setNewIds] = useState(() => new Set());

  // sections is rebuilt on every render of ChatInterface; observer setup
  // only depends on the ids, so key the effect off the joined id list.
  const idKey = sections.map((s) => s.id).join('|');
  const prevIdsRef = useRef(null);

  // While true, scrollspy observer updates are ignored: a programmatic
  // smooth scroll is in flight and its target owns the highlight.
  const suppressSpyRef = useRef(false);
  const suppressTimerRef = useRef(null);

  const endSpySuppression = () => {
    suppressSpyRef.current = false;
    if (suppressTimerRef.current != null) {
      clearTimeout(suppressTimerRef.current);
      suppressTimerRef.current = null;
    }
  };

  // Safety net if the component unmounts mid-scroll.
  useEffect(() => endSpySuppression, []);

  // Arrival detection: the first run baselines the ids already present at
  // mount (Question + Stage I, since this nav only mounts once a second
  // section exists) so nothing pulses on load. Every later run diffs new ids
  // against what was rendered before — sections that appear mid-run (the
  // user is reading earlier stages) are the ones that pulse.
  useEffect(() => {
    const ids = new Set(idKey ? idKey.split('|') : []);
    if (prevIdsRef.current == null) {
      prevIdsRef.current = ids;
      return;
    }
    const prev = prevIdsRef.current;
    const arrived = [...ids].filter((id) => !prev.has(id));
    if (arrived.length > 0) {
      setNewIds((cur) => {
        const next = new Set(cur);
        arrived.forEach((id) => next.add(id));
        return next;
      });
    }
    prevIdsRef.current = ids;
  }, [idKey]);

  // Auto-clear: once a just-arrived section scrolls into view (scrollspy
  // marks it current), it's been seen — drop its dot/pulse.
  useEffect(() => {
    if (!activeId || newIds.size === 0) return;
    if (newIds.has(activeId)) {
      setNewIds((cur) => {
        if (!cur.has(activeId)) return cur;
        const next = new Set(cur);
        next.delete(activeId);
        return next;
      });
    }
  }, [activeId, newIds]);

  useEffect(() => {
    const ids = idKey ? idKey.split('|') : [];
    const els = ids
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    if (els.length === 0) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
        // A clicked section owns the highlight until its smooth scroll
        // ends — ignore pass-through transitions during the jump.
        if (suppressSpyRef.current) return;
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top
          );
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      // Watch the upper slice of the scrollport; sections below the fold
      // are not "current".
      { rootMargin: '0px 0px -60% 0px', threshold: 0 }
    );

    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [idKey]);

  const jumpTo = (id) => {
    // Reading intent: suppress the live-run auto-follow pin so a heartbeat
    // can't stomp on the smooth scroll below (mid-jump scrollTop writes cancel
    // scrollIntoView and strand the section outside the spy band).
    onJump?.();
    const el = document.getElementById(id);
    // Optimistic highlight: the IntersectionObserver only reports
    // transitions, so if the entry's recorded state is already "not
    // intersecting but heading in", the callback may lag or coalesce behind
    // the animation. Setting it here makes the click feel immediate; the
    // observer still owns corrections while scrolling.
    setActiveId(id);
    // Own the highlight for the duration of the smooth scroll (see the
    // component docstring): suppression is ended by `scrollend`, with a
    // timer fallback for browsers without it and for no-op jumps.
    suppressSpyRef.current = true;
    suppressTimerRef.current = setTimeout(endSpySuppression, 1500);
    // `scroll` events don't bubble, but capture on window intercepts them
    // for any scroller — here the messages-container that scrollIntoView
    // drives.
    window.addEventListener('scrollend', endSpySuppression, {
      capture: true,
      once: true,
    });
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Move focus for keyboard users without fighting the smooth scroll.
    if (el && el.getAttribute('tabindex') === '-1') {
      el.focus({ preventScroll: true });
    }
    // Clicking a just-arrived section means it's been seen — clear the dot.
    setNewIds((cur) => {
      if (!cur.has(id)) return cur;
      const next = new Set(cur);
      next.delete(id);
      return next;
    });
  };

  if (sections.length === 0) {
    return null;
  }

  return (
    <nav className="stage-nav" aria-label="Council sections">
      {sections.map((section) => {
        const isActive = activeId === section.id;
        const isNew = newIds.has(section.id);
        return (
          <button
            key={section.id}
            type="button"
            className={`stage-nav-button${isNew ? ' is-new' : ''}`}
            aria-current={isActive ? 'true' : undefined}
            onClick={() => jumpTo(section.id)}
          >
            {section.numeral && (
              <span className="stage-nav-numeral" aria-hidden="true">
                {section.numeral}
              </span>
            )}
            {section.label}
            {isNew && (
              <span className="stage-nav-dot" aria-hidden="true" />
            )}
          </button>
        );
      })}
    </nav>
  );
}
