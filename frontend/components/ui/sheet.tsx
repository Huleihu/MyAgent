"use client";

import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

export const Sheet = Dialog.Root;
export const SheetTrigger = Dialog.Trigger;
export function SheetContent({ children }: { children: ReactNode }) { return <Dialog.Portal><Dialog.Overlay className="fixed inset-0 bg-black/40" /><Dialog.Content className="fixed inset-y-0 right-0 w-full max-w-md overflow-auto bg-white p-6 shadow-xl dark:bg-zinc-950">{children}</Dialog.Content></Dialog.Portal>; }
export const SheetTitle = Dialog.Title;
export const SheetClose = Dialog.Close;
