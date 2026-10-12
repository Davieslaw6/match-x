import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { ProbabilityBar, validP } from "./ProbabilityBar";
test("rejects probabilities that do not sum to 1", () => {
  expect(validP({ home: 0.5, draw: 0.5, away: 0.5 })).toBe(false);
});
test("renders accessible label", () => {
  render(<ProbabilityBar home={0.5} draw={0.25} away={0.25} label="Test" />);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("home 50.0%");
});
test("shows alert instead of fake numbers", () => {
  render(<ProbabilityBar home={0} draw={0} away={0} label="x" />);
  expect(screen.getByRole("alert")).toBeTruthy();
});
