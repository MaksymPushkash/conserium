"use client";

import { create } from "zustand";

interface UiState {
  debugOpen: boolean;
  setDebugOpen: (debugOpen: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  debugOpen: false,
  setDebugOpen: (debugOpen) => set({ debugOpen }),
}));
