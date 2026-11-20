import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PriorityOrder from "./PriorityOrder";

describe("PriorityOrder", () => {
  it("moves a dimension up and down", () => {
    const onChange = vi.fn();
    render(<PriorityOrder value={["impacto", "eficiencia", "flujo"]} onChange={onChange} />);
    fireEvent.click(screen.getByLabelText("Subir prioridad de Eficiencia"));
    expect(onChange).toHaveBeenLastCalledWith(["eficiencia", "impacto", "flujo"]);
    fireEvent.click(screen.getByLabelText("Bajar prioridad de Impacto"));
    expect(onChange).toHaveBeenLastCalledWith(["eficiencia", "impacto", "flujo"]);
  });

  it("disables the first up and last down buttons", () => {
    render(<PriorityOrder value={["flujo", "impacto", "eficiencia"]} onChange={() => {}} />);
    expect(screen.getByLabelText("Subir prioridad de Flujo")).toBeDisabled();
    expect(screen.getByLabelText("Bajar prioridad de Eficiencia")).toBeDisabled();
  });
});
