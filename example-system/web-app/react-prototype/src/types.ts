export type RequestKind = "repair" | "inspection";
export type Priority = "standard" | "urgent";

export interface ServiceRequest {
  id: string;
  title: string;
  type: RequestKind;
  priority: Priority;
  status: string;
  serialNumber?: string;
  justification?: string;
  createdAt: string;
}
