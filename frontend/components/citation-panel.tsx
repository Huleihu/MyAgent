"use client";

import { useState } from "react";
import type { Citation } from "@/lib/types";
import { Sheet, SheetClose, SheetContent, SheetTitle } from "@/components/ui/sheet";

export function CitationPanel({ citations }: { citations: Citation[] }) {
  const [selected, setSelected] = useState<Citation | null>(null);
  if (citations.length === 0) return <p>本轮没有 Citation。</p>;
  return <section><h2>Citations</h2>{citations.map((citation) => <button key={`${citation.doc_id}:${citation.chunk_id}`} onClick={() => setSelected(citation)}><strong>{citation.title}</strong><span>{citation.source}</span><span>{citation.snippet}</span></button>)}<Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>{selected && <SheetContent><SheetTitle>{selected.title}</SheetTitle><p>{selected.snippet}</p><p>{selected.doc_id} / {selected.chunk_id}</p><SheetClose>关闭</SheetClose></SheetContent>}</Sheet></section>;
}
