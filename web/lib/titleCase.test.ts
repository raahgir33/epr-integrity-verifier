import { describe, expect, it } from "vitest";
import { titleCase } from "./titleCase";

describe("titleCase", () => {
  it("lowercases a minor word in the middle", () => {
    expect(titleCase("A Guide to the API")).toBe("A Guide to the API");
  });

  it("capitalizes a minor word when it opens the string", () => {
    expect(titleCase("up and running")).toBe("Up and Running");
  });

  it("capitalizes a minor word when it closes the string", () => {
    expect(titleCase("what it is for")).toBe("What It Is For");
  });

  it("preserves an ID with a hyphen and digits exactly as written", () => {
    expect(titleCase("processor PWP-05 summary")).toBe("Processor PWP-05 Summary");
  });

  it("preserves an all-caps acronym exactly as written", () => {
    expect(titleCase("EPR certificate")).toBe("EPR Certificate");
    expect(titleCase("GSTIN lookup")).toBe("GSTIN Lookup");
  });

  it("preserves a mixed-case unit with a subscript digit", () => {
    expect(titleCase("tCO₂e avoided")).toBe("tCO₂e Avoided");
  });

  it("never touches Hindi text", () => {
    expect(titleCase("विवरण देखें")).toBe("विवरण देखें");
  });

  it("returns an empty string unchanged", () => {
    expect(titleCase("")).toBe("");
  });

  it("capitalizes a single word", () => {
    expect(titleCase("method")).toBe("Method");
  });

  it("capitalizes the base word of a contraction and lowercases the suffix", () => {
    expect(titleCase("who's afraid of the dark")).toBe("Who's Afraid of the Dark");
    expect(titleCase("don't stop")).toBe("Don't Stop");
  });
});
