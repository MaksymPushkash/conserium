"use client";

import { ArrowRight, Brain, FileText, MessageSquare, Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/stores/auth-store";

export default function LandingPage() {
  const accessToken = useAuthStore((state) => state.accessToken);

  return (
    <main className="min-h-screen overflow-x-hidden bg-black text-white">
      <div className="pointer-events-none fixed inset-0 opacity-70">
        <div className="absolute right-[-18rem] top-20 h-[48rem] w-[48rem] rounded-full border border-white/[0.03]" />
        <div className="absolute right-[-6rem] top-44 h-[36rem] w-[36rem] rounded-full border border-white/[0.025]" />
        <div className="absolute bottom-[-20rem] left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 rounded-full bg-white/[0.06] blur-3xl" />
      </div>

      <header className="fixed inset-x-0 top-0 z-50 border-b border-white/10 bg-black/80 backdrop-blur-xl transition-colors duration-500">
        <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="group flex items-center gap-3 transition-opacity duration-300 hover:opacity-80">
            <span className="text-lg font-normal tracking-tight">CORTEX</span>
            <span className="font-jetbrains rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-neutral-500 transition-colors duration-300 group-hover:border-white/20 group-hover:text-neutral-300">
              v0.1.0
            </span>
          </Link>
          <nav className="flex items-center gap-5 text-sm font-normal text-neutral-500">
            <a href="#philosophy" className="font-jetbrains hidden transition-colors duration-300 hover:text-white sm:block">
              PHILOSOPHY
            </a>
            <div className="hidden h-5 w-px bg-white/10 sm:block" />
            {accessToken ? (
              <Link href="/dashboard">
                <Button className="h-11 px-6">Open app</Button>
              </Link>
            ) : (
              <div className="flex items-center gap-2">
                <Link href="/auth">
                  <Button
                    variant="secondary"
                    className="h-11 px-5"
                  >
                    Sign in
                  </Button>
                </Link>
                <Link href="/auth?mode=register">
                  <Button className="h-11 px-5">
                    Sign up
                  </Button>
                </Link>
              </div>
            )}
          </nav>
        </div>
      </header>

      <section className="relative z-10 mx-auto max-w-7xl px-6 pb-24 pt-48 md:pt-52">
        <div className="animate-soft-in max-w-3xl">
          <h1 className="max-w-4xl text-5xl font-normal leading-[0.98] tracking-[-0.035em] text-white md:text-7xl">
            Save everything.
            <br />
            <span className="text-neutral-300">Ask naturally.</span>
            <br />
            <span className="bg-gradient-to-r from-neutral-300 via-neutral-500 to-neutral-800 bg-clip-text text-transparent">
              Know exactly why.
            </span>
          </h1>
          <p className="font-jetbrains mt-8 max-w-xl text-sm font-normal leading-8 text-neutral-500">
            Cortex turns PDFs, links, notes, audio, screenshots, and videos into a source-grounded workspace you can
            query like ChatGPT.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            {accessToken ? (
              <Link href="/dashboard">
                <Button className="h-12 px-6">
                  Open workspace
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            ) : (
              <>
                <Link href="/auth?mode=register">
                  <Button className="h-12 px-6">
                    Sign up
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/auth">
                  <Button
                    variant="secondary"
                    className="h-12 px-6"
                  >
                    Sign in
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>

        <ProductPreview />
      </section>

      <section id="philosophy" className="relative z-10 scroll-mt-24 border-y border-white/10 px-6 py-32">
        <div className="mx-auto max-w-3xl">
          <div className="font-jetbrains mb-10 text-xs font-normal uppercase tracking-[0.28em] text-neutral-600">
            PHILOSOPHY
          </div>
          <div className="text-xl font-normal leading-9 text-neutral-400 md:text-2xl md:leading-10">
            <p>your saved knowledge should not disappear into bookmarks, folders, and forgotten notes.</p>
            <br />
            <p>
              cortex keeps the archive calm: ingest asynchronously, retrieve with hybrid search, compress context with
              REFRAG, answer with citations.
            </p>
            <br />
            <p>the point is not more storage. the point is memory you can trust.</p>
          </div>
        </div>
      </section>

      <footer className="font-jetbrains relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-14 text-xs text-neutral-600">
        <span>© 2026 Cortex. All rights reserved.</span>
        <div className="flex gap-8">
          <span>Privacy</span>
          <span>Terms</span>
        </div>
      </footer>
    </main>
  );
}

function ProductPreview() {
  return (
    <div className="animate-soft-in mt-32 overflow-hidden rounded-xl border border-white/10 bg-black/60 shadow-2xl shadow-white/[0.03] [animation-delay:140ms]">
      <div className="grid min-w-[920px] grid-cols-[240px_1fr_300px]">
        <div className="border-r border-white/10 p-6">
          <div className="mb-8 text-sm font-semibold text-white">Cortex</div>
          <div className="space-y-3">
            <PreviewNav icon={FileText} label="Library" active />
            <PreviewNav icon={MessageSquare} label="Chat" />
            <PreviewNav icon={Brain} label="REFRAG" />
            <PreviewNav icon={Sparkles} label="Enrichment" />
          </div>
        </div>
        <div className="p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-white">Knowledge workspace</div>
              <div className="mt-1 text-xs text-neutral-600">5 sources processed · streaming answer ready</div>
            </div>
            <PreviewStatus status="READY" />
          </div>
          <div className="grid gap-3">
            {[
              ["Clean Architecture notes", "PDF · page-aware citations", "READY"],
              ["PostgreSQL pgvector article", "URL · hybrid retrieval", "READY"],
              ["Startup voice memo", "AUDIO · transcript generated", "PROCESSING"],
            ].map(([title, meta, status]) => (
              <div
                key={title}
                className="rounded-lg border border-white/10 bg-white/[0.035] p-4 transition-colors duration-300 hover:bg-white/[0.055]"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-medium text-neutral-200">{title}</div>
                    <div className="mt-1 text-xs text-neutral-600">{meta}</div>
                  </div>
                  <PreviewStatus status={status} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 rounded-lg border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-3 text-xs text-neutral-500">Ask Cortex</div>
            <div className="text-sm leading-6 text-neutral-300">
              What did I save about Clean Architecture and pgvector?
            </div>
            <div className="mt-4 text-sm leading-6 text-neutral-500">
              You saved notes about dependency direction and vector search tradeoffs. The strongest sources are{" "}
              <span className="text-white">[1]</span> and <span className="text-white">[2]</span>.
            </div>
          </div>
        </div>
        <div className="border-l border-white/10 bg-white/[0.02] p-6">
          <div className="mb-5 text-sm font-semibold text-white">Sources</div>
          <div className="space-y-3">
            {["Architecture Notes, page 3", "pgvector Guide", "REFRAG baseline"].map((source, index) => (
              <div
                key={source}
                className="rounded-lg border border-white/10 bg-black/50 p-3 transition-colors duration-300 hover:bg-white/[0.04]"
              >
                <div className="text-xs font-medium text-neutral-300">
                  [{index + 1}] {source}
                </div>
                <div className="mt-2 text-xs leading-5 text-neutral-600">
                  Retrieved, compressed, and mapped back to the original document.
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PreviewStatus({ status }: { status: string }) {
  const colors: Record<string, string> = {
    READY: "text-emerald-400",
    FAILED: "text-red-400",
    PROCESSING: "text-orange-400",
    QUEUED: "text-sky-400",
    PENDING: "text-neutral-500",
  };

  return (
    <span className={`font-jetbrains text-[10px] font-light uppercase ${colors[status] ?? colors.PENDING}`}>
      {status}
    </span>
  );
}

function PreviewNav({ icon: Icon, label, active = false }: { icon: typeof FileText; label: string; active?: boolean }) {
  return (
    <div
      className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors duration-300 ${
        active ? "bg-white text-black" : "text-neutral-500 hover:bg-white/[0.04] hover:text-neutral-300"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </div>
  );
}
