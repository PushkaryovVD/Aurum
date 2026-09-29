import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ContextualHelp } from "@/components/help/ContextualHelp";
import { HELP_TOPICS } from "@/lib/helpContent";
import { setLanguage } from "@/lib/i18n";
import { HelpPage } from "@/pages/HelpPage";

function render(node: React.ReactNode) {
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() => root.render(node));
  return { container, root };
}

afterEach(() => setLanguage("ru"));

describe("HelpPage", () => {
  it("covers every primary product area with links and concrete examples in English", () => {
    setLanguage("en");
    const view = render(
      <MemoryRouter>
        <HelpPage />
      </MemoryRouter>
    );

    expect(HELP_TOPICS).toHaveLength(15);
    expect(view.container.querySelectorAll("article")).toHaveLength(15);
    for (const topic of HELP_TOPICS) {
      expect(view.container.querySelector(`a[href="${topic.path}"]`)).not.toBeNull();
    }
    expect(view.container.textContent).toContain("Give every unit of income a job before you spend it");
    expect(view.container.textContent).toContain("A description containing “Coffee House” can go to Eating out");
    expect(view.container.textContent).toContain("A plan does not move money between bank accounts");

    act(() => view.root.unmount());
  });

  it("renders the same guide topics in Russian", () => {
    setLanguage("ru");
    const view = render(
      <MemoryRouter>
        <HelpPage />
      </MemoryRouter>
    );

    expect(view.container.querySelectorAll("article")).toHaveLength(HELP_TOPICS.length);
    expect(view.container.textContent).toContain("Заранее назначьте каждому тенге дохода задачу");
    expect(view.container.textContent).toContain("«Coffee House»");
    expect(view.container.textContent).toContain("План не переводит деньги между банковскими счетами");

    act(() => view.root.unmount());
  });

  it("wraps the table of contents instead of requiring horizontal scrolling", () => {
    const view = render(
      <MemoryRouter>
        <HelpPage />
      </MemoryRouter>
    );
    const contents = view.container.querySelector("nav");

    expect(contents?.className).toContain("flex-wrap");
    expect(contents?.className).not.toContain("overflow-x-auto");

    act(() => view.root.unmount());
  });
});

describe("ContextualHelp", () => {
  it("uses a touch-friendly button to disclose localized help without hover", () => {
    setLanguage("en");
    const view = render(<ContextualHelp topicId="envelopes" />);
    const button = view.container.querySelector("button");

    expect(button?.getAttribute("aria-expanded")).toBe("false");
    expect(button?.className).toContain("min-h-11");
    expect(view.container.textContent).not.toContain("A plan does not move money between bank accounts");

    act(() => button?.click());

    expect(button?.getAttribute("aria-expanded")).toBe("true");
    expect(view.container.textContent).toContain("A plan does not move money between bank accounts");

    act(() => view.root.unmount());
  });
});
