"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { getDocumentStatus, ingestDocument, ingestFile } from "@/lib/api";
import type { DocumentResponse, DocumentType } from "@/lib/types";
import { cn } from "@/lib/utils";

type Mode = "TEXT" | "URL" | "YOUTUBE" | "PDF" | "AUDIO" | "IMAGE";

const modes: Mode[] = ["TEXT", "URL", "YOUTUBE", "PDF", "AUDIO", "IMAGE"];

export default function IngestPage() {
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<Mode>("TEXT");
  const [title, setTitle] = useState("");
  const [language, setLanguage] = useState("");
  const [rawContent, setRawContent] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [trackedDocument, setTrackedDocument] = useState<DocumentResponse | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      if (mode === "PDF" || mode === "AUDIO" || mode === "IMAGE") {
        if (!file) throw new Error("Select a file first");
        return ingestFile(mode.toLowerCase() as "pdf" | "audio" | "image", {
          file,
          title: title || file.name,
          language: language || undefined,
        });
      }
      return ingestDocument({
        title,
        type: mode as DocumentType,
        raw_content: mode === "TEXT" ? rawContent : null,
        source_url: mode === "URL" || mode === "YOUTUBE" ? sourceUrl : null,
        language: language || null,
      });
    },
    onSuccess: (document) => {
      setTrackedDocument(document);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const statusQuery = useQuery({
    queryKey: ["document-status", trackedDocument?.id],
    queryFn: () => getDocumentStatus(trackedDocument!.id),
    enabled: Boolean(trackedDocument?.id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "READY" || status === "FAILED" ? false : 2000;
    },
  });

  const status = statusQuery.data;
  const canSubmit = useMemo(() => {
    if (!title.trim()) return false;
    if (mode === "TEXT") return Boolean(rawContent.trim());
    if (mode === "URL" || mode === "YOUTUBE") return Boolean(sourceUrl.trim());
    return Boolean(file);
  }, [file, mode, rawContent, sourceUrl, title]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-6 p-4 md:grid-cols-[1fr_360px] md:p-8">
      <section className="space-y-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Ingest content</h1>
          <p className="font-jetbrains mt-2 max-w-2xl text-xs leading-6 text-neutral-600">
            Queue documents through the backend pipeline and poll their Redis status until ready.
          </p>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>New source</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {modes.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={cn(
                      "font-jetbrains inline-flex h-10 items-center justify-center rounded-md border px-4 text-sm tracking-normal transition-colors",
                      mode === item
                        ? "border-white bg-white text-black"
                        : "border-white/10 bg-white/[0.04] text-white hover:bg-white/10",
                    )}
                    style={{ fontWeight: 300 }}
                    onClick={() => setMode(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title" className="font-jetbrains"/>
                <Input
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                  placeholder="Language, optional"
                  className="font-jetbrains"
                />
              </div>
              {mode === "TEXT" ? (
                <Textarea
                  value={rawContent}
                  onChange={(event) => setRawContent(event.target.value)}
                  placeholder="Paste notes, markdown, or raw text"
                  className="font-jetbrains min-h-56"
                />
              ) : null}
              {mode === "URL" || mode === "YOUTUBE" ? (
                <Input
                  value={sourceUrl}
                  onChange={(event) => setSourceUrl(event.target.value)}
                  placeholder={mode === "YOUTUBE" ? "YouTube URL" : "Article URL"}
                  className="font-jetbrains"
                />
              ) : null}
              {mode === "PDF" || mode === "AUDIO" || mode === "IMAGE" ? (
                <Input type="file" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
              ) : null}
              {mutation.error ? (
                <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  {mutation.error instanceof Error ? mutation.error.message : "Ingestion failed"}
                </div>
              ) : null}
              <Button disabled={!canSubmit || mutation.isPending}>{mutation.isPending ? "Queueing..." : "Queue ingestion"}</Button>
            </form>
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {trackedDocument ? (
              <>
                <div>
                  <div className="font-medium">{trackedDocument.title}</div>
                  <div className="mt-1 text-xs text-neutral-500">{trackedDocument.id}</div>
                </div>
                <StatusPill status={status?.status ?? trackedDocument.status} />
                <Progress value={status?.progress ?? 0} />
                <div className="text-sm text-neutral-600">{status?.message ?? "Waiting for worker status..."}</div>
              </>
            ) : (
              <div className="font-jetbrains text-xs text-neutral-500">Submit content to start polling status.</div>
            )}
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
