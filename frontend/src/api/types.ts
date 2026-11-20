export interface Journal {
  id: number;
  origin: "etl" | "lider" | "manual";
  title: string;
  issn_print: string | null;
  issn_electronic: string | null;
  issn_normalized: string | null;
  url: string | null;
  publisher: string | null;
  country: string | null;
  language: string | null;
  access_type: string | null;
  quartile: string | null;
  publindex_category: string | null;
  apc_usd: number | null;
  apc_text: string | null;
  apc_status: "sin_costo" | "con_costo" | "desconocido";
  weeks_to_publication: number | null;
  time_text: string | null;
  h_index: number | null;
  sjr: number | null;
  citescore: number | null;
  impact_factor: number | null;
  quality_cost_index: number | null;
  submission_format: string | null;
  article_types: string | null;
  issues_per_year: string | null;
  topics: string[];
  locally_modified: boolean;
}

export interface JournalDetail extends Journal {
  keywords: string | null;
  contact_email: string | null;
  sources: string[];
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface JournalPage {
  items: Journal[];
  total: number;
  page: number;
  page_size: number;
}

/** Campos editables (lo que acepta POST/PATCH). */
export type JournalInput = Partial<
  Pick<
    JournalDetail,
    | "title" | "issn_print" | "issn_electronic" | "url" | "publisher" | "country" | "language"
    | "keywords" | "contact_email" | "access_type" | "quartile" | "publindex_category"
    | "apc_usd" | "apc_text" | "weeks_to_publication" | "time_text" | "h_index" | "sjr"
    | "citescore" | "impact_factor" | "submission_format" | "article_types" | "issues_per_year"
    | "topics"
  >
>;

export interface FacetValue {
  value: string;
  count: number;
}

export interface Facets {
  topics: FacetValue[];
  quartiles: FacetValue[];
  access_types: FacetValue[];
  countries: FacetValue[];
  languages: FacetValue[];
  submission_formats: FacetValue[];
  publindex_categories: FacetValue[];
  origins: FacetValue[];
  apc_statuses: FacetValue[];
  total: number;
  max_apc_usd: number | null;
  max_weeks: number | null;
  max_h_index: number | null;
}

export interface ImportReport {
  dry_run: boolean;
  mode: string;
  rows: number;
  created: number;
  updated: number;
  skipped: number;
  invalid: number;
  duplicates: string[];
  errors: string[];
}

export type Dimension = "impacto" | "eficiencia" | "flujo";

export interface RecommendRequest {
  title: string;
  abstract: string;
  keywords: string;
  language: "auto" | "es" | "en";
  priority_order: Dimension[];
  top_k: number;
}

export interface JournalSummary {
  id: number;
  title: string;
  url: string | null;
  country: string | null;
  access_type: string | null;
  quartile: string | null;
  publindex_category: string | null;
  apc_usd: number | null;
  apc_status: Journal["apc_status"];
  weeks_to_publication: number | null;
  h_index: number | null;
  topics: string[];
}

export interface RecommendedJournal {
  rank: number;
  issn: string;
  journal: JournalSummary | null;
  score_tfidf: number | null;
  score_scibert: number | null;
  score_tematico: number | null;
  score_calidad_costo: number | null;
  score_final: number | null;
}

export interface ModelInfo {
  available: boolean;
  alpha: number | null;
  journals_covered: number | null;
  catalog_total: number | null;
  tfidf_features: number | null;
  scibert_model: string | null;
  quality_weight: number | null;
}

export interface RecommendResponse {
  model: ModelInfo;
  priority_order: Dimension[];
  results: RecommendedJournal[];
}
