import { useEffect, useState } from 'react';
import './StageNav.css';

/**
 * Sticky section jump-nav, rendered above the stage sections of an
 * assistant message. Lets the reader hop between the question and each
 * stage (I / II / III) without scrolling through the full transcript.
 *
 * Active section is tracked with an IntersectionObserver (scrollspy):
 * the topmost section crossing the upper band of the scrollport is
 * considered current and its button highlighted.
 */
export default function StageNav({ sections }) {
  const [activeId, setActiveId] = useState(null);

  // sections is rebuilt on every render of ChatInterface; observer setup
  // only depends on the ids, so key the effect off the joined id list.
  const idKey = sections.map((s) => s.id).join('|');

  useEffect(() => {
    const ids = idKey ? idKey.split('|') : [];
    const els = ids
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    if (els.length === 0) return undefined;

    const observer = new IntersectionObserver(
      (entries) => {
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
    const el = document.getElementById(id);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Move focus for keyboard users without fighting the smooth scroll.
    if (el && el.getAttribute('tabindex') === '-1') {
      el.focus({ preventScroll: true });
    }
  };

  if (sections.length === 0) {
    return null;
  }

  return (
    <nav className="stage-nav" aria-label="Council sections">
      {sections.map((section) => {
        const isActive = activeId === section.id;
        return (
          <button
            key={section.id}
            type="button"
            className="stage-nav-button"
            aria-current={isActive ? 'true' : undefined}
            onClick={() => jumpTo(section.id)}
          >
            {section.numeral && (
              <span className="stage-nav-numeral" aria-hidden="true">
                {section.numeral}
              </span>
            )}
            {section.label}
          </button>
        );
      })}
    </nav>
  );
}
