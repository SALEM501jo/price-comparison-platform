/**
 * The mark that follows one listing through the Lab: the form row, both
 * rankings and its score card all show the same letter, so a reader can
 * trace a listing without re-reading its title. Neutral on purpose -- colour
 * in the rankings means something else (see RankComparison).
 */
export default function LetterBadge({ letter, className = '' }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gray-100 text-xs font-bold text-gray-700 dark:bg-gray-800 dark:text-gray-200 ${className}`}
    >
      {letter}
    </span>
  );
}
