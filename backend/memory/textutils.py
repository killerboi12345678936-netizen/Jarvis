
import re


STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "then", "of", "to",
    "in", "on", "at", "for", "with", "by", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "this", "that", "these",
    "those", "i", "you", "he", "she", "we", "they", "my", "your",
    "our", "their", "as", "so", "not", "no", "do", "does", "did",
    "have", "has", "had", "will", "would", "can", "could", "should",
})


def tokenize(text):
    if not text:
        return set()

    words = re.findall(r"[a-z0-9]+", text.lower())

    return {
        word for word in words
        if word not in STOPWORDS and len(word) > 1
    }


def token_jaccard(tokens_a, tokens_b):
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)

    if not intersection:
        return 0.0

    return intersection / len(tokens_a | tokens_b)


def text_similarity(text_a, text_b):
    return token_jaccard(tokenize(text_a), tokenize(text_b))
