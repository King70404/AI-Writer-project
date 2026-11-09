import { vi } from "vitest";
import {
  analysisEstimateClient,
  type SendEstimate,
} from "../../frontend/src/features/usage/api/budget";

export function allowedAnalysisEstimate(
  overrides: Partial<SendEstimate> = {},
): SendEstimate {
  return {
    estimate_method: "utf8_bytes_upper_v1",
    profile_id: "default-local",
    input_characters: 10,
    input_tokens_upper: 30,
    output_tokens_upper: 2048,
    price: null,
    estimated_cost_upper: null,
    currency: null,
    budget_mode: "off",
    budget_currency: null,
    task_limit: null,
    monthly_limit: null,
    task_spent_upper: null,
    month_spent_upper: null,
    unpriced_attempts: 0,
    decision: "allowed",
    reasons: [],
    ...overrides,
  };
}
export function allowFakeAnalysisEstimates() {
  vi.spyOn(analysisEstimateClient, "reference").mockResolvedValue(
    allowedAnalysisEstimate(),
  );
  vi.spyOn(analysisEstimateClient, "review").mockResolvedValue(
    allowedAnalysisEstimate(),
  );
}
