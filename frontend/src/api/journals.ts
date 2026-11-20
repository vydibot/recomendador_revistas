import { api } from "./client";
import { type Filters, filtersToParams } from "@/lib/filters";
import type { Facets, ImportReport, JournalDetail, JournalInput, JournalPage } from "./types";

export const PAGE_SIZE = 24;

export const listJournals = (filters: Filters) => {
  const params = filtersToParams(filters);
  params.set("page_size", String(PAGE_SIZE));
  return api<JournalPage>("/journals", { params });
};

export const getFacets = () => api<Facets>("/journals/facets");

export const createJournal = (body: JournalInput, force = false) =>
  api<JournalDetail>("/journals", {
    method: "POST",
    body,
    params: new URLSearchParams(force ? { force: "true" } : {}),
  });

export const updateJournal = (id: number, body: JournalInput, force = false) =>
  api<JournalDetail>(`/journals/${id}`, {
    method: "PATCH",
    body,
    params: new URLSearchParams(force ? { force: "true" } : {}),
  });

export const deleteJournal = (id: number) => api<void>(`/journals/${id}`, { method: "DELETE" });

export const getJournal = (id: number) => api<JournalDetail>(`/journals/${id}`);

export const importCsv = (file: File, mode: "skip" | "update" | "add", dryRun: boolean) => {
  const form = new FormData();
  form.append("file", file);
  return api<ImportReport>("/journals/import", {
    method: "POST",
    form,
    params: new URLSearchParams({ mode, dry_run: String(dryRun) }),
  });
};
