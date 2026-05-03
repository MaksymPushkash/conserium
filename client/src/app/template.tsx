import { AppShell } from "@/components/app-shell";

export default function Template({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
