"use client";

import { Github } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { login, oauthUrl, register } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

type Mode = "login" | "register";

export default function AuthPage() {
  return (
    <Suspense fallback={<AuthShell />}>
      <AuthContent />
    </Suspense>
  );
}

function AuthContent() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useAuthStore((state) => state.setSession);
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (params.get("mode") === "register") {
      setMode("register");
    }
  }, [params]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens =
        mode === "login"
          ? await login({ email, password })
          : await register({ email, password, display_name: displayName || null });
      setSession(tokens.access_token, tokens.refresh_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <Card className="w-full max-w-md border-white/10 bg-black/70 shadow-2xl shadow-white/5">
        <CardHeader>
          <CardTitle>{mode === "login" ? "Sign in to Cortex" : "Create your Cortex account"}</CardTitle>
          <p className="font-jetbrains pt-2 text-xs leading-6 text-neutral-500">
            Search saved documents, stream answers, and inspect citations from one quiet workspace.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={onSubmit} className="space-y-3">
            {mode === "register" ? (
              <Input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Display name"
                className="font-jetbrains"
              />
            ) : null}
            <Input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" className="font-jetbrains" />
            <Input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              type="password"
              className="font-jetbrains"
            />
            {error ? <div className="rounded-md border border-red-500/30 bg-red-500/10 p-2 text-sm text-red-300">{error}</div> : null}
            <Button className="w-full" disabled={submitting}>
              {submitting ? "Working..." : mode === "login" ? "Sign in" : "Sign up"}
            </Button>
          </form>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" onClick={() => (window.location.href = oauthUrl("google"))}>
              Google
            </Button>
            <Button variant="secondary" onClick={() => (window.location.href = oauthUrl("github"))}>
              <Github className="h-4 w-4" />
              GitHub
            </Button>
          </div>
          <Button variant="ghost" className="w-full" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "Need an account?" : "Already have an account?"}
          </Button>
        </CardContent>
      </Card>
    </AuthShell>
  );
}

function AuthShell({ children }: { children?: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-black text-white">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute right-0 top-0 h-[34rem] w-[34rem] rounded-full bg-white/[0.04] blur-3xl" />
        <div className="absolute bottom-[-12rem] left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-white/[0.05] blur-3xl" />
      </div>
      <header className="relative z-10 mx-auto flex h-24 max-w-7xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-3">
          <span className="text-lg font-normal tracking-tight">CORTEX</span>
          <span className="font-jetbrains rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-xs text-neutral-500">
            v0.1.0
          </span>
        </Link>
        <Link href="/" className="text-sm font-normal text-neutral-500 hover:text-white">
          Back
        </Link>
      </header>
      <section className="relative z-10 mx-auto grid min-h-[calc(100vh-6rem)] max-w-7xl grid-cols-1 items-center gap-12 px-6 pb-16 lg:grid-cols-[1fr_440px]">
        <div className="hidden lg:block">
          <h1 className="max-w-3xl text-6xl font-normal leading-[0.95] tracking-[-0.04em]">
            Your archive.
            <br />
            <span className="text-neutral-400">Queryable.</span>
            <br />
            <span className="text-neutral-700">Traceable.</span>
          </h1>
        </div>
        <div className="flex justify-center">{children}</div>
      </section>
    </main>
  );
}
