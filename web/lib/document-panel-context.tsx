"use client";

import { createContext, useContext } from "react";

/** T13.5 plan, Part 4: lets EvidenceLink open a document in the processor
 * page's slide-over side panel instead of a new browser tab, wherever a
 * provider is in scope. Components rendered outside the processor page's
 * tab tree (e.g. a reasoning timeline rendered outside the tabs during a live
 * run) see no provider and keep the original new-tab link behaviour. */
const DocumentPanelContext = createContext<((docId: string) => void) | null>(null);

export const DocumentPanelProvider = DocumentPanelContext.Provider;

export function useDocumentPanel(): ((docId: string) => void) | null {
  return useContext(DocumentPanelContext);
}
