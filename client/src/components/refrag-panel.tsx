import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RefragContext } from "@/lib/types";

export function RefragPanel({ context }: { context: RefragContext | null | undefined }) {
  if (!context) {
    return <div className="text-sm text-neutral-500">No REFRAG context yet.</div>;
  }

  const selected = [...context.full_text_chunks, ...context.compressed_chunks];

  return (
    <Card className="border-white/10 bg-white/[0.015]">
      <CardHeader>
        <CardTitle className="text-lg font-normal text-white">REFRAG context</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 text-xs">
          <Metric label="strategy" value={context.compression_strategy} />
          <div className="grid grid-cols-2 gap-2">
            <Metric label="original tokens" value={String(context.total_original_tokens)} />
            <Metric label="context tokens" value={String(context.total_context_tokens)} />
          </div>
        </div>
        <div className="space-y-3">
          {selected.map((chunk) => (
            <div key={chunk.chunk_id} className="rounded-md border border-white/10 bg-black/40 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="truncate text-sm font-light text-white">{chunk.document_title ?? "Untitled"}</div>
                <Badge className="font-jetbrains font-light">{chunk.representation}</Badge>
              </div>
              <p className="line-clamp-4 text-xs font-light leading-5 text-neutral-300">{chunk.context_text}</p>
              <div className="font-jetbrains mt-2 text-xs font-light text-neutral-500">
                {chunk.citation ?? "not cited"} · chunk {chunk.chunk_index}
                {chunk.page_number ? ` · page ${chunk.page_number}` : ""}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border border-white/10 bg-black/40 p-2">
      <div className="font-jetbrains truncate text-neutral-500">{label}</div>
      <div className="font-jetbrains mt-1 break-words font-light leading-5 text-white">{value}</div>
    </div>
  );
}
