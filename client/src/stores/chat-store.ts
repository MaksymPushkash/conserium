"use client";

import { create } from "zustand";

import type { QuerySource, RefragContext } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: QuerySource[];
  refragContext?: RefragContext;
  evalScores?: Record<string, unknown>;
  traceId?: string | null;
}

interface ChatState {
  conversationId: string | null;
  selectedSourceId: string | null;
  messages: ChatMessage[];
  setConversationId: (conversationId: string | null) => void;
  setSelectedSourceId: (sourceId: string | null) => void;
  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void;
  resetConversation: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  conversationId: null,
  selectedSourceId: null,
  messages: [],
  setConversationId: (conversationId) => set({ conversationId }),
  setSelectedSourceId: (selectedSourceId) => set({ selectedSourceId }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, patch) =>
    set((state) => ({
      messages: state.messages.map((message) => (message.id === id ? { ...message, ...patch } : message)),
    })),
  resetConversation: () => set({ conversationId: null, selectedSourceId: null, messages: [] }),
}));
