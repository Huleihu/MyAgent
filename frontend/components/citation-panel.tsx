"use client";

import { useState } from "react";

import { Sheet, SheetClose, SheetContent, SheetTitle } from "@/components/ui/sheet";
import type { Citation } from "@/lib/types";

/** 展示当前回合的引用，并在抽屉中显示单条引用详情。 */
export function CitationPanel({ citations }: { citations: Citation[] }) {
  const [selected, setSelected] = useState<Citation | null>(null);
  if (citations.length === 0) return null;

  return <section className="citation-panel" aria-label="本轮引用">
    <div className="section-title"><div><p className="eyebrow">来源依据</p><h2>引用</h2></div><span>{citations.length}</span></div>
    <div className="citation-grid">
      {citations.map((citation, index) => <button className="citation-card" key={`${citation.doc_id}:${citation.chunk_id}`} onClick={() => setSelected(citation)}>
        <span className="citation-index">{String(index + 1).padStart(2, "0")}</span>
        <span className="citation-title">{citation.title}</span>
        <span className="citation-snippet">{citation.snippet}</span>
        <span className="citation-source">{citation.source}</span>
      </button>)}
    </div>
    <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
      {selected && <SheetContent><SheetTitle>{selected.title}</SheetTitle><p>{selected.snippet}</p><p className="citation-detail-id">{selected.doc_id} / {selected.chunk_id}</p><SheetClose>关闭</SheetClose></SheetContent>}
    </Sheet>
  </section>;
}
