import { createContext, useContext, type ReactNode } from "react";

export interface Settings {
  units: "metric" | "imperial";
  dateFormat: "iso" | "local";
}

const defaults: Settings = { units: "metric", dateFormat: "iso" };
const SettingsContext = createContext<Settings>(defaults);

export function SettingsProvider({ children }: { children: ReactNode }) {
  return <SettingsContext.Provider value={defaults}>{children}</SettingsContext.Provider>;
}

export function useSettings(): Settings {
  return useContext(SettingsContext);
}
