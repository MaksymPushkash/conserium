"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getMetricsText, listDocuments } from "@/lib/api";
import { useChatStore } from "@/stores/chat-store";

export default function DebugPage() {
  const metricsQuery = useQuery({ queryKey: ["metrics"], queryFn: getMetricsText, refetchInterval: 10_000 });
  const documentsQuery = useQuery({ queryKey: ["documents", "debug"], queryFn: () => listDocuments({ limit: 100 }), refetchInterval: 10_000 });
  const messages = useChatStore((state) => state.messages);
  const latestAssistant = [...messages].reverse().find((message) => message.role === "assistant");

  const byStatus = (documentsQuery.data?.items ?? []).reduce<Record<string, number>>((acc, document) => {
    acc[document.status] = (acc[document.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-normal tracking-normal">Debug</h1>
          <p className="font-jetbrains mt-2 text-xs text-neutral-500">Development surface for backend health, REFRAG, scores, and worker signals.</p>
        </div>
        <Button
          variant="secondary"
          onClick={() => {
            void metricsQuery.refetch();
            void documentsQuery.refetch();
          }}
        >
          <RefreshCcw className="h-4 w-4" />
          Refresh
        </Button>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent>
            <div className="font-jetbrains text-sm text-neutral-500">Documents</div>
            <div className="mt-2 text-2xl font-normal">{documentsQuery.data?.total ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="font-jetbrains text-sm text-neutral-500">Conversation messages</div>
            <div className="mt-2 text-2xl font-normal">{messages.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="font-jetbrains text-sm text-neutral-500">Trace</div>
            <div className="mt-2 truncate text-sm font-normal">{latestAssistant?.traceId ?? "none"}</div>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Document status summary</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="font-jetbrains overflow-auto rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-neutral-300">
              {JSON.stringify(byStatus, null, 2)}
            </pre>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Latest query debug</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="font-jetbrains max-h-96 overflow-auto rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-neutral-300">
              {JSON.stringify(
                {
                  eval_scores: latestAssistant?.evalScores,
                  trace_id: latestAssistant?.traceId,
                  refrag_context: latestAssistant?.refragContext,
                  sources: latestAssistant?.sources,
                },
                null,
                2,
              )}
            </pre>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Prometheus metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <pre className="font-jetbrains max-h-[520px] overflow-auto rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-neutral-300">
            {metricsQuery.data ?? "Metrics unavailable."}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
