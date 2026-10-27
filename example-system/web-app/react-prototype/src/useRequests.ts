import { useEffect, useState } from "react";
import { loadRequests, makeRequest } from "./requestService";
import type { ServiceRequest } from "./types";

// walkthrough:react-hook:start
export function useRequests() {
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let current = true;
    loadRequests()
      .then((data) => {
        if (current) setRequests(data);
      })
      .catch(() => {
        if (current) setLoadError("Request list could not be loaded.");
      });
    return () => {
      current = false;
    };
  }, []);

  function addRequest(input: Omit<ServiceRequest, "id" | "status" | "createdAt">) {
    setRequests((items) => [makeRequest(input), ...items]);
  }

  return { requests, addRequest, loadError };
}
// walkthrough:react-hook:end
