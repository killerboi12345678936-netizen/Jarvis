
# Sentence segmentation for progressive text-to-speech. Mirrors the
# frontend splitter so streamed text and spoken text stay in sync.

SENTENCE_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "eg", "ie", "fig", "approx", "dept", "est", "inc", "ltd", "co",
    "corp", "rev", "hon", "capt", "sgt", "gen", "col", "lt", "mt",
    "ft", "apt", "no", "al", "cf", "viz", "ph", "md", "min", "max",
    "sec", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "sept", "oct", "nov", "dec",
}

SENTENCE_CLOSERS = {'"', "'", ")", "]", "}", "`", "*"}

SENTENCE_PUNCTUATION = {".", "!", "?"}


import re


def _ends_with_abbreviation(text):
    match = re.search(r"([A-Za-z]+)\s*$", text)

    if not match:
        return False

    word = match.group(1).lower()

    return word in SENTENCE_ABBREVIATIONS or len(word) == 1


def _ends_with_list_item_number(text):
    line_start = text.rfind("\n") + 1

    return bool(re.fullmatch(r"\d+", text[line_start:]))


def extract_complete_sentences(buffer):
    """Split complete sentences off the buffer.

    Returns (sentences, remaining) where sentences is a list of
    strings and remaining is the unconsumed tail.
    """

    boundaries = []
    length = len(buffer)

    i = 0
    while i < length:
        char = buffer[i]

        if char not in SENTENCE_PUNCTUATION:
            i += 1
            continue

        end = i

        while end + 1 < length and buffer[end + 1] in SENTENCE_PUNCTUATION:
            end += 1

        while end + 1 < length and buffer[end + 1] in SENTENCE_CLOSERS:
            end += 1

        at_end = end + 1 >= length
        next_char = "" if at_end else buffer[end + 1]
        before = buffer[:i]

        if char == ".":
            is_list_number = (
                bool(re.match(r"\s", next_char))
                and _ends_with_list_item_number(before)
            )

            is_decimal_or_truncated = (
                bool(re.search(r"\d$", before))
                and (bool(re.match(r"\d", next_char)) or at_end)
            )

            if (
                _ends_with_abbreviation(before)
                or is_list_number
                or is_decimal_or_truncated
            ):
                i = end + 1
                continue

        if not at_end and not re.match(r"\s", next_char):
            i = end + 1
            continue

        boundaries.append(end)
        i = end + 1

    sentences = []
    consumed = 0

    for boundary in boundaries:
        sentences.append(buffer[consumed:boundary + 1])
        consumed = boundary + 1

    return sentences, buffer[consumed:]
