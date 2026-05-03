"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Database, FileText, MessageSquare, Upload } from "lucide-react";
import Link from "next/link";

import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUser, listDocuments } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export default function DashboardPage() {
  const userQuery = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const documentsQuery = useQuery({ queryKey: ["documents", { limit: 5 }], queryFn: () => listDocuments({ limit: 5 }) });
  const documents = documentsQuery.data?.items ?? [];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 p-4 md:p-8">
      <header className="flex flex-col justify-between gap-4 border-b border-neutral-800 pb-6 md:flex-row md:items-end">
        <div>
          <div className="font-jetbrains text-sm text-neutral-500">
            Signed in as {userQuery.data?.email ?? "loading..."}
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal text-white">Knowledge workspace</h1>
        </div>
        <div className="flex gap-2">
          <Link href="/ingest">
            <Button>
              <Upload className="h-4 w-4" />
              Ingest
            </Button>
          </Link>
          <Link href="/chat">
            <Button variant="secondary">
              <MessageSquare className="h-4 w-4" />
              Ask
            </Button>
          </Link>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard icon={Database} label="Documents" value={String(documentsQuery.data?.total ?? 0)} />
        <MetricCard icon={FileText} label="Recent items" value={String(documents.length)} />
        <MetricCard icon={MessageSquare} label="Conversation" value="Ready" />
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Recent documents</CardTitle>
          <Link href="/documents" className="flex items-center gap-1 text-sm text-neutral-500 hover:text-white">
            View all <ArrowRight className="h-4 w-4" />
          </Link>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-neutral-900">
            {documents.map((document) => (
              <Link
                key={document.id}
                href={`/documents/${document.id}`}
                className="grid gap-3 py-3 hover:bg-neutral-950 md:grid-cols-[1fr_auto]"
              >
                <div>
                  <div className="font-medium text-white">{document.title}</div>
                  <div className="font-jetbrains text-sm text-neutral-500">{formatDateTime(document.created_at)}</div>
                </div>
                <div className="font-jetbrains flex items-center gap-3 self-center justify-self-start md:justify-self-end">
                  <span className="font-jetbrains text-sm font-light leading-none text-neutral-500">{document.type}</span>
                  <StatusPill status={document.status} />
                </div>
              </Link>
            ))}
            {!documents.length ? <div className="py-8 text-sm text-neutral-500">No documents yet.</div> : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({ icon: Icon, label, value }: { icon: typeof Database; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between">
        <div>
          <div className="font-jetbrains text-sm text-neutral-500">{label}</div>
          <div className="mt-2 text-2xl font-semibold text-white">{value}</div>
        </div>
        <Icon className="h-5 w-5 text-neutral-500" />
      </CardContent>
    </Card>
  );
}
