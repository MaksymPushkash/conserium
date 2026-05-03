"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, MessageSquare, Plus, RotateCcw, Send, Sparkles } from "lucide-react";
import { FormEvent, useMemo, useRef, useState } from "react";

import { RefragPanel } from "@/components/refrag-panel";
import { SourceCard } from "@/components/source-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createChat, getChat, listChats, queryDocuments, streamQueryDocuments } from "@/lib/api";
import type { ChatMessageResponse, QuerySource, RefragContext } from "@/lib/types";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/stores/chat-store";
import { useChatStore } from "@/stores/chat-store";
import { useUiStore } from "@/stores/ui-store";

export default function ChatPage() {
  const [query, setQuery] = useState("");
  const [topicTitle, setTopicTitle] = useState("");
  const [streaming, setStreaming] = useState(true);
  const controllerRef = useRef<AbortController | null>(null);
  const queryClient = useQueryClient();
  const {
    conversationId,
    setConversationId,
    messages,
    setMessages,
    addMessage,
    updateMessage,
    resetConversation,
  } = useChatStore();
  const { debugOpen, setDebugOpen } = useUiStore();

  const chatsQuery = useQuery({
    queryKey: ["chats"],
    queryFn: () => listChats({ limit: 50 }),
  });
  const createChatMutation = useMutation({
    mutationFn: createChat,
    onSuccess: async (chat) => {
      setConversationId(chat.id);
      setMessages([]);
      setTopicTitle("");
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
    },
  });
  const syncMutation = useMutation({ mutationFn: queryDocuments });

  const latestAssistant = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant"),
    [messages],
  );
  const selectedChat = chatsQuery.data?.items.find((chat) => chat.id === conversationId);

  async function selectChat(chatId: string) {
    const detail = await queryClient.fetchQuery({
      queryKey: ["chats", chatId],
      queryFn: () => getChat(chatId),
    });
    setConversationId(chatId);
    setMessages(detail.messages.map(toChatMessage));
  }

  function startLocalNewChat() {
    controllerRef.current?.abort();
    resetConversation();
  }

  async function createTopic(event: FormEvent) {
    event.preventDefault();
    await createChatMutation.mutateAsync({ title: topicTitle.trim() || "New chat" });
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (!text) return;
    setQuery("");
    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    addMessage({ id: userMessageId, role: "user", content: text });
    addMessage({ id: assistantMessageId, role: "assistant", content: "" });

    if (!streaming) {
      try {
        const result = await syncMutation.mutateAsync({ query: text, conversation_id: conversationId, limit: 5 });
        setConversationId(result.conversation_id);
        updateMessage(assistantMessageId, {
          content: result.answer,
          sources: result.sources,
          refragContext: result.refrag_context,
        });
        await queryClient.invalidateQueries({ queryKey: ["chats"] });
        await queryClient.invalidateQueries({ queryKey: ["chats", result.conversation_id] });
      } catch (error) {
        updateMessage(assistantMessageId, { content: error instanceof Error ? error.message : "Query failed" });
      }
      return;
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    let answer = "";
    let sources: QuerySource[] = [];
    let refragContext: RefragContext | undefined;
    let activeConversationId = conversationId;

    try {
      await streamQueryDocuments(
        { query: text, conversation_id: conversationId, limit: 5 },
        async (event) => {
          if (event.event === "metadata") {
            const nextConversationId = event.data.conversation_id;
            if (typeof nextConversationId === "string") {
              activeConversationId = nextConversationId;
              setConversationId(nextConversationId);
            }
          }
          if (event.event === "token") {
            const token = typeof event.data.text === "string" ? event.data.text : "";
            answer += token;
            updateMessage(assistantMessageId, { content: answer });
          }
          if (event.event === "sources" && Array.isArray(event.data.sources)) {
            sources = event.data.sources as QuerySource[];
            updateMessage(assistantMessageId, { sources });
          }
          if (event.event === "refrag_context") {
            refragContext = event.data as unknown as RefragContext;
            updateMessage(assistantMessageId, { refragContext });
          }
          if (event.event === "done") {
            updateMessage(assistantMessageId, {
              sources,
              refragContext,
              evalScores: event.data.eval_scores as Record<string, unknown> | undefined,
              traceId: typeof event.data.trace_id === "string" ? event.data.trace_id : null,
            });
            await queryClient.invalidateQueries({ queryKey: ["chats"] });
            if (activeConversationId) {
              await queryClient.invalidateQueries({ queryKey: ["chats", activeConversationId] });
            }
          }
          if (event.event === "error") {
            updateMessage(assistantMessageId, { content: String(event.data.message ?? "Stream failed") });
          }
        },
        controller.signal,
      );
    } catch (error) {
      updateMessage(assistantMessageId, { content: error instanceof Error ? error.message : "Stream failed" });
    } finally {
      controllerRef.current = null;
    }
  }

  return (
    <div className="min-h-screen px-4 py-6 md:px-8">
      <div className="mx-auto grid max-w-[1640px] gap-6 xl:grid-cols-[260px_minmax(0,1fr)_360px]">
        <aside className="hidden xl:block">
          <div className="sticky top-6 space-y-4">
            <Card className="border-white/10 bg-white/[0.015]">
              <CardHeader>
                <CardTitle className="text-lg font-normal text-white">Chats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={createTopic} className="space-y-2">
                  <Input
                    value={topicTitle}
                    onChange={(event) => setTopicTitle(event.target.value)}
                    placeholder="New topic"
                    className="font-jetbrains text-sm font-light"
                  />
                  <Button type="submit" className="w-full font-normal" disabled={createChatMutation.isPending}>
                    <Plus className="h-4 w-4" />
                    Create chat
                  </Button>
                </form>
                <Button variant="secondary" className="w-full font-normal" onClick={startLocalNewChat}>
                  <MessageSquare className="h-4 w-4" />
                  Temporary chat
                </Button>
                <div className="space-y-2">
                  {chatsQuery.data?.items.map((chat) => (
                    <button
                      key={chat.id}
                      type="button"
                      onClick={() => void selectChat(chat.id)}
                      className={cn(
                        "w-full rounded-lg border px-3 py-3 text-left transition-colors",
                        chat.id === conversationId
                          ? "border-white/20 bg-white/[0.08]"
                          : "border-white/10 bg-transparent hover:border-white/20 hover:bg-white/[0.03]",
                      )}
                    >
                      <div className="truncate text-sm font-normal text-white">{chat.title}</div>
                      <div className="font-jetbrains mt-1 text-xs font-light text-neutral-500">
                        {chat.message_count} messages
                      </div>
                    </button>
                  ))}
                  {!chatsQuery.data?.items.length ? (
                    <div className="font-jetbrains rounded-lg border border-white/10 px-3 py-4 text-xs font-light leading-5 text-neutral-500">
                      Create a topic chat or ask a question to start one.
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </div>
        </aside>

        <section className="flex min-h-[calc(100vh-48px)] flex-col rounded-xl border border-white/10 bg-white/[0.015]">
          <header className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-normal tracking-normal text-white">{selectedChat?.title ?? "Query"}</h1>
              <div className="font-jetbrains mt-1 text-xs font-light text-neutral-500">
                conversation {conversationId ?? "new"}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={streaming ? "default" : "secondary"}
                size="sm"
                onClick={() => setStreaming((value) => !value)}
                className="font-normal"
              >
                {streaming ? "Streaming" : "Sync"}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setDebugOpen(!debugOpen)} className="font-normal">
                <Bug className="h-4 w-4" />
                Debug
              </Button>
              <Button variant="ghost" size="icon" onClick={startLocalNewChat} aria-label="Reset conversation">
                <RotateCcw className="h-4 w-4" />
              </Button>
            </div>
          </header>

          <div className="flex-1 overflow-auto px-5 py-8">
            <div className="mx-auto flex min-h-full max-w-4xl flex-col justify-end gap-5">
              {messages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "max-w-[82%] rounded-xl border px-4 py-3 text-sm font-light leading-6",
                    message.role === "user"
                      ? "ml-auto border-white bg-white text-black shadow-[0_0_36px_rgba(255,255,255,0.08)]"
                      : "mr-auto border-white/10 bg-white/[0.035] text-neutral-100",
                  )}
                >
                  <div className="whitespace-pre-wrap">{message.content || "..."}</div>
                  {message.sources?.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.sources.map((source, index) => {
                        const citation = source.citation ?? `[${index + 1}]`;
                        return (
                        <a
                          key={source.chunk_id}
                          href={`#source-${citation.replace(/\D/g, "")}`}
                          className="font-jetbrains rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs font-light text-neutral-300 transition-colors hover:border-white/30 hover:text-white"
                        >
                          {citation} {source.document_title ?? "source"}
                        </a>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ))}
              {!messages.length ? (
                <div className="mx-auto flex max-w-2xl flex-1 flex-col items-center justify-center py-24 text-center">
                  <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
                    <Sparkles className="h-4 w-4 text-neutral-300" />
                  </div>
                  <h2 className="text-4xl font-light tracking-normal text-white">Ask your archive.</h2>
                  <p className="font-jetbrains mt-4 max-w-xl text-sm font-light leading-6 text-neutral-500">
                    Create topic chats for Python learning, finance notes, architecture research, or any archive thread.
                  </p>
                  <div className="mt-8 flex flex-wrap justify-center gap-2">
                    {["python learning", "clean architecture", "summarize this PDF", "pgvector mentions"].map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => setQuery(suggestion)}
                        className="font-jetbrains rounded-full border border-white/10 px-3 py-1.5 text-xs font-light text-neutral-500 transition-colors hover:border-white/30 hover:text-neutral-200"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>

          <form onSubmit={onSubmit} className="border-t border-white/10 p-4">
            <div className="mx-auto flex max-w-4xl gap-3 rounded-xl border border-white/10 bg-black p-2 shadow-[0_-20px_60px_rgba(0,0,0,0.35)]">
              <Textarea
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask about this topic..."
                className="font-jetbrains min-h-12 resize-none border-0 bg-transparent px-2 text-white placeholder:text-neutral-600 focus-visible:ring-0"
              />
              <Button size="icon" disabled={!query.trim()} className="mt-auto h-11 w-11 rounded-lg">
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </form>
        </section>

        <aside className="hidden xl:block">
          <div className="sticky top-6 max-h-[calc(100vh-48px)] space-y-4 overflow-auto">
            <Card className="border-white/10 bg-white/[0.015]">
              <CardHeader>
                <CardTitle className="text-lg font-normal text-white">Sources</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {latestAssistant?.sources?.length ? (
                  latestAssistant.sources.map((source, index) => (
                    <SourceCard key={source.chunk_id} source={source} index={index + 1} />
                  ))
                ) : (
                  <div className="font-jetbrains text-xs font-light leading-6 text-neutral-500">
                    Sources will appear after retrieval.
                  </div>
                )}
              </CardContent>
            </Card>
            {debugOpen ? <RefragPanel context={latestAssistant?.refragContext} /> : null}
            {debugOpen && latestAssistant?.evalScores ? (
              <Card className="border-white/10 bg-white/[0.015]">
                <CardHeader>
                  <CardTitle className="text-lg font-normal text-white">Eval / trace</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="font-jetbrains overflow-auto rounded-md border border-white/10 bg-black p-3 text-xs font-light leading-5 text-neutral-300">
                    {JSON.stringify({ eval_scores: latestAssistant.evalScores, trace_id: latestAssistant.traceId }, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            ) : null}
          </div>
        </aside>
      </div>
    </div>
  );
}

function toChatMessage(message: ChatMessageResponse): ChatMessage {
  return {
    id: message.id,
    role: message.role === "user" || message.role === "assistant" || message.role === "system" ? message.role : "system",
    content: message.content,
    sources: message.sources ?? undefined,
    refragContext: message.refrag_context ?? undefined,
    evalScores: message.eval_scores ?? undefined,
    traceId: message.trace_id,
  };
}
