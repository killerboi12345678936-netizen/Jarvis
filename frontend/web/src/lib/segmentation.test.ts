import { describe, expect, it } from "vitest";

import { extractCompleteSentences } from "./segmentation";

describe("extractCompleteSentences", () => {
  it("splits complete sentences and keeps the tail", () => {
    const { sentences, remaining } = extractCompleteSentences(
      "Hello there. How are you? I am",
    );

    expect(sentences).toEqual(["Hello there.", " How are you?"]);
    expect(remaining).toBe(" I am");
  });

  it("returns nothing when no boundary exists", () => {
    const { sentences, remaining } = extractCompleteSentences(
      "still thinking",
    );

    expect(sentences).toEqual([]);
    expect(remaining).toBe("still thinking");
  });

  it("does not split on abbreviations", () => {
    const { sentences, remaining } = extractCompleteSentences(
      "Dr. Smith arrived. Then we",
    );

    expect(sentences).toEqual(["Dr. Smith arrived."]);
    expect(remaining).toBe(" Then we");
  });

  it("does not split decimals", () => {
    const { sentences, remaining } = extractCompleteSentences(
      "Pi is 3.14 exactly",
    );

    expect(sentences).toEqual([]);
    expect(remaining).toBe("Pi is 3.14 exactly");
  });

  it("keeps list numbers with their items", () => {
    const { sentences } = extractCompleteSentences(
      "Plan:\n1. Review notes\n2. Practice",
    );

    expect(sentences).toEqual([]);
  });

  it("includes trailing closers in the sentence", () => {
    const { sentences, remaining } = extractCompleteSentences(
      'He said "Go." Then left',
    );

    expect(sentences).toEqual(['He said "Go."']);
    expect(remaining).toBe(" Then left");
  });

  it("consumes progressively across feeds", () => {
    let pending = "";

    const feeds = ["Good mo", "rning! Today", " we study. More"];

    let all: string[] = [];

    for (const chunk of feeds) {
      pending += chunk;

      const { sentences, remaining } = extractCompleteSentences(pending);

      all = all.concat(sentences);

      pending = remaining;
    }

    expect(all).toEqual(["Good morning!", " Today we study."]);
    expect(pending).toBe(" More");
  });
});
