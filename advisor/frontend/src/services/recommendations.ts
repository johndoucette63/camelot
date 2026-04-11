import type { RecommendationsResponse } from "../types";

export async function fetchRecommendations(): Promise<RecommendationsResponse> {
  const res = await fetch("/api/recommendations");
  if (!res.ok) {
    throw new Error(`Failed to fetch recommendations: ${res.status}`);
  }
  return (await res.json()) as RecommendationsResponse;
}
