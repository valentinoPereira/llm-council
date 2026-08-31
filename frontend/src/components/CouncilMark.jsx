/**
 * The council-table monogram: six members seated around a ring with a small
 * central chamber point, reading as a seal rather than a generic gear. Colors
 * inherit `currentColor`. Same geometry as public/council.svg (the favicon).
 */
export default function CouncilMark({ className }) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="13" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <circle cx="32" cy="19" r="3.4" fill="currentColor" />
      <circle cx="43.3" cy="25.5" r="3.4" fill="currentColor" />
      <circle cx="43.3" cy="38.5" r="3.4" fill="currentColor" />
      <circle cx="32" cy="45" r="3.4" fill="currentColor" />
      <circle cx="20.7" cy="38.5" r="3.4" fill="currentColor" />
      <circle cx="20.7" cy="25.5" r="3.4" fill="currentColor" />
      <circle cx="32" cy="32" r="2" fill="currentColor" />
    </svg>
  );
}
