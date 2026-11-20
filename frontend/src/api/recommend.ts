import { api } from "./client";
import type { ModelInfo, RecommendRequest, RecommendResponse } from "./types";

export const getModelInfo = () => api<ModelInfo>("/recommend/model");

export const recommend = (body: RecommendRequest) =>
  api<RecommendResponse>("/recommend", { method: "POST", body });
