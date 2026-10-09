/** Chicago-style title case (T13.5b plan, Part 2) for static UI chrome
 * copy only — headings, section titles, button/CTA labels, tab labels.
 * Never call this on body text, data values, memos or document content
 * (Heading/SectionTitle/Button/Tabs only apply it to literal string
 * children, never to interpolated data — see their own call sites).
 *
 * Minor words (articles, coordinating conjunctions, short prepositions)
 * are lowercased unless they open or close the string, per Chicago Manual
 * of Style's title-case convention. */
const MINOR_WORDS = new Set([
  "a",
  "an",
  "and",
  "as",
  "at",
  "but",
  "by",
  "for",
  "if",
  "in",
  "nor",
  "of",
  "on",
  "or",
  "per",
  "so",
  "the",
  "to",
  "up",
  "via",
  "yet",
]);

const DEVANAGARI = /[ऀ-ॿ]/;
const HAS_DIGIT = /[0-9]/;
// lead / main letter-run / optional contraction suffix ('s, 't, 're, ...) / trail
const WORD_SHAPE = /^([^A-Za-z]*)([A-Za-z]+)('[A-Za-z]*)?([^A-Za-z]*)$/;

function capitalize(letters: string): string {
  return letters.charAt(0).toUpperCase() + letters.slice(1).toLowerCase();
}

/** A token is left byte-for-byte untouched if any of: it contains
 * Devanagari (Hindi text must never be touched); it's already fully
 * uppercase (acronyms/IDs like EPR, GSTIN); it contains a hyphen
 * (PWP-05) or underscore (a tool/field identifier like read_document —
 * found live in the reasoning log's title-cased action line, where
 * "Called read_document" became "Called Read_document" without this
 * rule, since an underscore-joined identifier shouldn't be word-split
 * and capitalized any more than a hyphenated one should); it contains
 * an ASCII digit; or it has an uppercase letter after its first *letter*
 * — this last rule is what preserves "tCO₂e" (no hyphen/underscore, no
 * ASCII digit — the ₂ is a Unicode subscript, not \d — but it IS
 * already mixed-case, which is enough on its own). */
function shouldPreserve(token: string): boolean {
  if (DEVANAGARI.test(token)) return true;
  const letters = token.replace(/[^A-Za-z]/g, "");
  if (letters.length === 0) return false;
  const isAllCaps = letters.length > 1 && letters === letters.toUpperCase();
  const hasInternalUpper = /[A-Z]/.test(letters.slice(1));
  return isAllCaps || token.includes("-") || token.includes("_") || HAS_DIGIT.test(token) || hasInternalUpper;
}

export function titleCase(input: string): string {
  if (!input) return input;

  const parts = input.split(/(\s+)/); // keep whitespace runs so spacing round-trips exactly
  const wordIndices = parts.reduce<number[]>((acc, part, i) => {
    if (part.trim() !== "") acc.push(i);
    return acc;
  }, []);
  if (wordIndices.length === 0) return input;
  const firstWordIndex = wordIndices[0];
  const lastWordIndex = wordIndices[wordIndices.length - 1];

  return parts
    .map((part, i) => {
      if (part.trim() === "") return part; // whitespace run, pass through
      if (shouldPreserve(part)) return part;

      const match = part.match(WORD_SHAPE);
      if (!match) return part; // punctuation-only token (e.g. "&", "—")
      const [, lead, letters, contraction, trail] = match;

      const isEdge = i === firstWordIndex || i === lastWordIndex;
      const finalLetters =
        !isEdge && MINOR_WORDS.has(letters.toLowerCase()) ? letters.toLowerCase() : capitalize(letters);
      // A contraction suffix ("'s", "'t", "'re"...) always stays lowercase,
      // regardless of the word it's attached to or its position.
      return `${lead}${finalLetters}${(contraction ?? "").toLowerCase()}${trail}`;
    })
    .join("");
}
