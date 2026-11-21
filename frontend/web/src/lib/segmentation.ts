// Words after which a period does not end a sentence, plus single-letter
// initials such as "J." or the "e." in "e.g.".
export const SENTENCE_ABBREVIATIONS = new Set([
  "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
  "eg", "ie", "fig", "approx", "dept", "est", "inc", "ltd", "co",
  "corp", "rev", "hon", "capt", "sgt", "gen", "col", "lt", "mt",
  "ft", "apt", "no", "al", "cf", "viz", "ph", "md", "min", "max",
  "sec", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
  "sept", "oct", "nov", "dec",
]);

// Quotes, brackets, and markdown emphasis that may trail sentence punctuation.
export const SENTENCE_CLOSERS = new Set([
  "\"", "'", ")", "]", "}", "`", "*",
]);

export const endsWithAbbreviation = (text: string) => {
  const match = /([A-Za-z]+)\s*$/.exec(text);

  if (!match) return false;

  const word = match[1].toLowerCase();

  return SENTENCE_ABBREVIATIONS.has(word) || word.length === 1;
};

export const endsWithListItemNumber = (text: string) => {
  const lineStart = text.lastIndexOf("\n") + 1;

  return /^\d+$/.test(text.slice(lineStart));
};

export const extractCompleteSentences = (
  buffer: string,
): { sentences: string[]; remaining: string } => {
  const boundaries: number[] = [];

  for (let i = 0; i < buffer.length; i += 1) {
    if (!".!?".includes(buffer[i])) {
      continue;
    }

    let end = i;

    while (
      end + 1 < buffer.length &&
      ".!?".includes(buffer[end + 1])
    ) {
      end += 1;
    }

    while (
      end + 1 < buffer.length &&
      SENTENCE_CLOSERS.has(buffer[end + 1])
    ) {
      end += 1;
    }

    const atEnd = end + 1 >= buffer.length;
    const nextChar = atEnd ? "" : buffer[end + 1];
    const before = buffer.slice(0, i);

    // Periods that belong to abbreviations ("Dr.", "e.g."), numbered
    // markdown lists ("1. Item"), decimals ("3.14"), or a number whose
    // continuation has not arrived yet do not end a sentence.
    if (buffer[i] === ".") {
      const isListNumber =
        /\s/.test(nextChar) && endsWithListItemNumber(before);

      const isDecimalOrTruncatedNumber =
        /\d$/.test(before) && (/\d/.test(nextChar) || atEnd);

      if (
        endsWithAbbreviation(before) ||
        isListNumber ||
        isDecimalOrTruncatedNumber
      ) {
        i = end;
        continue;
      }
    }

    // A punctuation run only completes a sentence when followed by
    // whitespace or the end of the currently buffered text.
    if (!atEnd && !/\s/.test(nextChar)) {
      i = end;
      continue;
    }

    boundaries.push(end);
    i = end;
  }

  if (boundaries.length === 0) {
    return { sentences: [], remaining: buffer };
  }

  const sentences: string[] = [];
  let consumed = 0;

  for (const boundary of boundaries) {
    sentences.push(buffer.slice(consumed, boundary + 1));
    consumed = boundary + 1;
  }

  return { sentences, remaining: buffer.slice(consumed) };
};
