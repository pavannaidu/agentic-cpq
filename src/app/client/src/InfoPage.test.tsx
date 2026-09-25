import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InfoPage } from "./InfoPage";

describe("Agentic CPQ info page", () => {
  it("explains the value proposition and governed architecture", () => {
    render(<InfoPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Agentic CPQ on Databricks" })).toBeInTheDocument();
    expect(screen.getByText("Agent proposes.")).toBeInTheDocument();
    expect(screen.getByText("Governed data prices.")).toBeInTheDocument();
    expect(screen.getByText("Server validates.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Genie Agent" })).toBeInTheDocument();
    expect(screen.getByText("Unity Catalog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Web Search" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cited public web" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Lakebase" })).toBeInTheDocument();
    expect(screen.getByLabelText("Prompt + current draft")).toBeInTheDocument();
    expect(screen.getByLabelText("Proposed SKUs + quantities")).toBeInTheDocument();
    expect(screen.getByLabelText("Validated quote update")).toBeInTheDocument();
    expect(screen.getByLabelText("Agent runtime to Genie Agent")).toBeInTheDocument();
    expect(screen.getByLabelText("Agent runtime to Web Search")).toBeInTheDocument();
    expect(screen.getByLabelText("Agent runtime and CPQ validation to Lakebase")).toBeInTheDocument();
    expect(screen.getByText("Cannot authorize pricing, SKUs, accounts, or approvals")).toBeInTheDocument();
  });

  it("links back to the quote workspace", () => {
    render(<InfoPage />);

    expect(screen.getByRole("link", { name: "Quote workspace" })).toHaveAttribute("href", "/");
  });
});
