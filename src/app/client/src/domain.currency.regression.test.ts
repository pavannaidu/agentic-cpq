import { describe, expect, it } from "vitest";
import { currency } from "./domain";

describe("currency display precision", () => {
  it("preserves meaningful cents while omitting an unnecessary zero fraction", () => {
    expect(currency.format(1_234)).toBe("$1,234");
    expect(currency.format(1_234.5)).toBe("$1,234.50");
    expect(currency.format(1_234.56)).toBe("$1,234.56");
  });
});
