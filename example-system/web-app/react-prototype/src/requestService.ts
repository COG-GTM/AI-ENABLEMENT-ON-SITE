import type { ServiceRequest } from "./types";

export async function loadRequests(): Promise<ServiceRequest[]> {
  const response = await fetch("/requests.json");
  if (!response.ok) throw new Error("Request list could not be loaded.");
  return response.json() as Promise<ServiceRequest[]>;
}

export function makeRequest(
  input: Omit<ServiceRequest, "id" | "status" | "createdAt">
): ServiceRequest {
  return {
    ...input,
    id: `REQ-${Date.now()}`,
    status: "open",
    createdAt: new Date().toISOString()
  };
}
