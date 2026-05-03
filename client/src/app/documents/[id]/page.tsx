"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { StatusPill } from "@/components/status-pill";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getDocument, getDocumentStatus } from "@/lib/api";
import { compactId, formatDateTime } from "@/lib/utils";

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const documentQuery = useQuery({
    queryKey: ["document", params.id],
    queryFn: () => getDocument(params.id),
    refetchInterval: (query) => {
      const document = query.state.data;
      if (!document || document.status === "FAILED") {
        return false;
      }
      return hasVisibleEnrichment(document) ? false : 5000;
    },
  });
  const statusQuery = useQuery({
    queryKey: ["document-status", params.id],
    queryFn: () => getDocumentStatus(params.id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "READY" || status === "FAILED" ? false : 2000;
    },
  });
  const document = documentQuery.data;

  if (documentQuery.isLoading) {
    return <div className="p-8 text-sm text-neutral-500">Loading document...</div>;
  }

  if (!document) {
    return <div className="p-8 text-sm text-neutral-500">Document not found.</div>;
  }

  return (
    <div className="mx-auto grid max-w-6xl gap-10 p-4 md:grid-cols-[1fr_360px] md:p-10">
      <section className="space-y-10">
        <div>
          <Link href="/documents">
            <Button className="h-9 px-4 text-sm">Back to library</Button>
          </Link>
        </div>
        <header className="space-y-5">
          <div className="font-jetbrains flex flex-wrap gap-2">
            <StatusPill status={statusQuery.data?.status ?? document.status} />
            <Badge>{document.type}</Badge>
            {document.language ? <Badge>{document.language}</Badge> : null}
          </div>
          <div>
            <h1 className="text-3xl font-normal tracking-normal text-white">{document.title}</h1>
            <p className="font-jetbrains mt-4 text-sm text-neutral-500">{compactId(document.id)} · {formatDateTime(document.created_at)}</p>
          </div>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>Content</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="whitespace-pre-wrap text-sm leading-7 text-white">
              {document.raw_content ?? "No raw content returned."}
            </pre>
          </CardContent>
        </Card>
      </section>

      <aside className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row label="status"  value={String(statusQuery.data?.status ?? document.status)} />
            <Row label="progress" value={`${statusQuery.data?.progress ?? 0}%`} />
            <Row label="message" value={statusQuery.data?.message ?? "—"} />
            <Row label="word count" value={String(document.word_count ?? "—")} />
            <Row label="source" value={document.source_url ?? document.file_path ?? "—"} />
            <Row label="duplicate" value={document.is_duplicate ? `yes · ${document.duplicate_of_id}` : "no"} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Enrichment</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <TagBlock title="Tags" values={document.tags} />
            <JsonBlock title="Entities" value={document.entities} />
            <JsonBlock title="Categories" value={document.categories} />
            <JsonBlock title="Visual metadata" value={document.visual_metadata} />
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function hasVisibleEnrichment(document: NonNullable<Awaited<ReturnType<typeof getDocument>>>) {
  return Boolean(
    document.tags.length ||
      document.entities?.length ||
      document.categories?.length ||
      document.visual_metadata ||
      document.is_duplicate,
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[100px_1fr] gap-5 border-b border-white/10 pb-3">
      <div className="font-jetbrains text-neutral-500">{label}</div>
      <div className="break-words text-neutral-100">{value}</div>
    </div>
  );
}

function TagBlock({ title, values }: { title: string; values: string[] }) {
  return (
    <div>
      <div className="mb-3 text-sm font-normal text-neutral-100">{title}</div>
      <div className="font-jetbrains flex flex-wrap gap-2">
        {values.length ? values.map((value) => <Badge key={value}>{value}</Badge>) : <span className="text-sm text-neutral-500">None</span>}
      </div>
    </div>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div>
      <div className="mb-3 text-sm font-normal text-neutral-100">{title}</div>
      <pre className="font-jetbrains max-h-48 overflow-auto rounded-md border border-white/10 bg-black p-3 text-xs leading-5 text-neutral-300">
        {value ? JSON.stringify(value, null, 2) : "None"}
      </pre>
    </div>
  );
}
