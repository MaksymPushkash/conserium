"use client";

import { useEffect } from "react";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/stores/auth-store";

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={<CallbackShell />}>
      <OAuthCallbackContent />
    </Suspense>
  );
}

function OAuthCallbackContent() {
  const router = useRouter();
  const params = useSearchParams();
  const setSession = useAuthStore((state) => state.setSession);

  useEffect(() => {
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    if (accessToken && refreshToken) {
      setSession(accessToken, refreshToken);
      router.replace("/");
    }
  }, [params, router, setSession]);

  return <CallbackShell />;
}

function CallbackShell() {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Completing OAuth login</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-neutral-600">
          Waiting for the backend to hand off `access_token` and `refresh_token`. If you see a JSON response from the
          backend instead, configure the backend OAuth callback to redirect here with those tokens.
        </CardContent>
      </Card>
    </main>
  );
}
