"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Code2,
  FileText,
  Heading1,
  Heading2,
  Heading3,
  ImagePlus,
  List,
  ListOrdered,
  Minus,
  Plus,
  Quote,
  Trash2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createNote, deleteNote, getNote, ingestFile, listNotes, updateNote } from "@/lib/api";
import type { Note, NoteListItem, NoteListResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const AUTOSAVE_DELAY_MS = 1400;

type SlashRange = {
  start: number;
  end: number;
  query: string;
};

type SlashCommand = {
  id: string;
  label: string;
  shortcut: string;
  icon: LucideIcon;
  createReplacement?: (content: string) => { text: string; cursorOffset?: number };
  imageUpload?: true;
};

const slashCommands: SlashCommand[] = [
  { id: "h1", label: "Heading 1", shortcut: "H1", icon: Heading1, createReplacement: () => ({ text: "# " }) },
  { id: "h2", label: "Heading 2", shortcut: "H2", icon: Heading2, createReplacement: () => ({ text: "## " }) },
  { id: "h3", label: "Heading 3", shortcut: "H3", icon: Heading3, createReplacement: () => ({ text: "### " }) },
  { id: "bullet", label: "Bullet List", shortcut: "-", icon: List, createReplacement: () => ({ text: "- " }) },
  { id: "ordered", label: "Ordered List", shortcut: "1.", icon: ListOrdered, createReplacement: () => ({ text: "1. " }) },
  { id: "quote", label: "Quote", shortcut: ">", icon: Quote, createReplacement: () => ({ text: "> " }) },
  { id: "code", label: "Code Block", shortcut: "</>", icon: Code2, createReplacement: () => ({ text: "```\n\n```", cursorOffset: 4 }) },
  { id: "divider", label: "Divider", shortcut: "-", icon: Minus, createReplacement: () => ({ text: "---" }) },
  { id: "image", label: "Image Upload", shortcut: "img", icon: ImagePlus, imageUpload: true },
  {
    id: "toc",
    label: "Table of Contents",
    shortcut: "toc",
    icon: FileText,
    createReplacement: (content) => ({ text: buildTableOfContents(content) }),
  },
];

function serializeNote(title: string, content: string) {
  return `${title.trim() || "Untitled"}\n${content}`;
}

function noteToListItem(note: Note): NoteListItem {
  return {
    id: note.id,
    title: note.title,
    status: note.status,
    word_count: note.word_count,
    language: note.language,
    created_at: note.created_at,
    updated_at: note.updated_at,
  };
}

function upsertNoteList(old: NoteListResponse | undefined, note: Note): NoteListResponse {
  const item = noteToListItem(note);
  if (!old) {
    return { items: [item], total: 1, limit: 100, offset: 0 };
  }
  const exists = old.items.some((item) => item.id === note.id);
  return {
    ...old,
    items: exists ? old.items.map((oldItem) => (oldItem.id === note.id ? item : oldItem)) : [item, ...old.items],
    total: exists ? old.total : old.total + 1,
  };
}

function buildTableOfContents(content: string) {
  const headings = content
    .split("\n")
    .map((line) => line.match(/^(#{1,3})\s+(.+)$/))
    .filter((match): match is RegExpMatchArray => Boolean(match))
    .map((match) => {
      const depth = match[1].length;
      const label = match[2].trim();
      return `${"  ".repeat(depth - 1)}- ${label}`;
    });
  return headings.length ? headings.join("\n") : "- Add headings to build a table of contents";
}

function findSlashRange(value: string, cursor: number): SlashRange | null {
  const lineStart = value.lastIndexOf("\n", cursor - 1) + 1;
  const lastSpace = value.lastIndexOf(" ", cursor - 1);
  const tokenStart = Math.max(lineStart, lastSpace + 1);
  const token = value.slice(tokenStart, cursor);
  if (!token.startsWith("/") || token.includes("\n")) return null;
  return { start: tokenStart, end: cursor, query: token.slice(1).toLowerCase() };
}

export default function NotesPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [loadedNoteId, setLoadedNoteId] = useState<string | null>(null);
  const [slashRange, setSlashRange] = useState<SlashRange | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const pendingImageRangeRef = useRef<SlashRange | null>(null);
  const lastSavedRef = useRef("");

  const notesQuery = useQuery({
    queryKey: ["notes"],
    queryFn: () => listNotes({ limit: 200 }),
  });

  const notes = useMemo(() => notesQuery.data?.items ?? [], [notesQuery.data?.items]);
  const selectedListItem = notes.find((note) => note.id === selectedId) ?? null;
  const selectedNoteQuery = useQuery({
    queryKey: ["notes", selectedId],
    queryFn: () => getNote(selectedId as string),
    enabled: Boolean(selectedId),
  });
  const selectedNote = selectedNoteQuery.data ?? null;
  const filteredSlashCommands = useMemo(() => {
    if (!slashRange) return [];
    if (!slashRange.query) return slashCommands;
    return slashCommands.filter((command) => {
      const haystack = `${command.label} ${command.shortcut}`.toLowerCase();
      return haystack.includes(slashRange.query);
    });
  }, [slashRange]);

  const createMutation = useMutation({
    mutationFn: () => createNote({ title: "Untitled", content: "" }),
    onSuccess: (note) => {
      queryClient.setQueryData<NoteListResponse>(["notes"], (old) => upsertNoteList(old, note));
      queryClient.setQueryData(["notes", note.id], note);
      setSelectedId(note.id);
      setLoadedNoteId(note.id);
      setTitle(note.title);
      setContent(note.content);
      lastSavedRef.current = serializeNote(note.title, note.content);
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!selectedId) throw new Error("Select a note first");
      return updateNote(selectedId, {
        title: title.trim() || "Untitled",
        content,
        language: null,
      });
    },
    onSuccess: (note) => {
      queryClient.setQueryData<NoteListResponse>(["notes"], (old) => upsertNoteList(old, note));
      queryClient.setQueryData(["notes", note.id], note);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      lastSavedRef.current = serializeNote(note.title, note.content);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteNote,
    onSuccess: (_, deletedId) => {
      queryClient.setQueryData<NoteListResponse>(["notes"], (old) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.filter((note) => note.id !== deletedId),
          total: Math.max(0, old.total - 1),
        };
      });
      if (selectedId === deletedId) {
        setSelectedId(null);
        setLoadedNoteId(null);
        setTitle("");
        setContent("");
        lastSavedRef.current = "";
      }
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const imageUploadMutation = useMutation({
    mutationFn: (file: File) => ingestFile("image", { file, title: file.name }),
    onSuccess: (document) => {
      const range = pendingImageRangeRef.current;
      pendingImageRangeRef.current = null;
      if (!range) return;
      insertTextAtRange(`![${document.title}](document:${document.id})`, range);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  useEffect(() => {
    if (!selectedId && notes.length) {
      setSelectedId(notes[0].id);
    }
  }, [notes, selectedId]);

  useEffect(() => {
    if (!selectedNote || loadedNoteId === selectedNote.id) return;
    setLoadedNoteId(selectedNote.id);
    setTitle(selectedNote.title);
    setContent(selectedNote.content);
    lastSavedRef.current = serializeNote(selectedNote.title, selectedNote.content);
  }, [loadedNoteId, selectedNote]);

  useEffect(() => {
    if (!selectedId || updateMutation.isPending || loadedNoteId !== selectedId) return;
    const snapshot = serializeNote(title, content);
    if (snapshot === lastSavedRef.current) return;
    const timeout = window.setTimeout(() => {
      updateMutation.mutate();
    }, AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timeout);
  }, [content, loadedNoteId, selectedId, title, updateMutation]);

  useEffect(() => {
    setSlashIndex(0);
  }, [slashRange?.query]);

  const saveState = updateMutation.isPending
    ? "saving"
    : selectedListItem?.status === "READY"
      ? "indexed"
      : selectedListItem?.status.toLowerCase() || "draft";

  function setCaret(position: number) {
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(position, position);
    });
  }

  function insertTextAtRange(text: string, range: SlashRange, cursorOffset = text.length) {
    const next = `${content.slice(0, range.start)}${text}${content.slice(range.end)}`;
    setContent(next);
    setSlashRange(null);
    setCaret(range.start + cursorOffset);
  }

  function runSlashCommand(command: SlashCommand) {
    if (!slashRange) return;
    if (command.imageUpload) {
      pendingImageRangeRef.current = slashRange;
      setSlashRange(null);
      imageInputRef.current?.click();
      return;
    }
    const replacement = command.createReplacement?.(content);
    if (!replacement) return;
    insertTextAtRange(replacement.text, slashRange, replacement.cursorOffset ?? replacement.text.length);
  }

  function onContentChange(event: ChangeEvent<HTMLTextAreaElement>) {
    const next = event.target.value;
    const cursor = event.target.selectionStart;
    setContent(next);
    setSlashRange(findSlashRange(next, cursor));
  }

  function onContentKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!slashRange || !filteredSlashCommands.length) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setSlashRange(null);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setSlashIndex((index) => (index + 1) % filteredSlashCommands.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setSlashIndex((index) => (index - 1 + filteredSlashCommands.length) % filteredSlashCommands.length);
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      event.preventDefault();
      runSlashCommand(filteredSlashCommands[slashIndex] ?? filteredSlashCommands[0]);
    }
  }

  return (
    <div className="min-h-screen px-4 py-6 md:px-8">
      <div className="mx-auto grid max-w-[1640px] gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="hidden xl:block">
          <div className="sticky top-6">
            <Card className="border-white/10 bg-white/[0.015]">
              <CardHeader className="flex flex-row items-center justify-between space-y-0">
                <div>
                  <CardTitle className="text-lg font-normal text-white">Notes</CardTitle>
                  <div className="font-jetbrains mt-1 text-xs font-light text-neutral-500">{notes.length} saved</div>
                </div>
                <Button
                  size="icon"
                  variant="secondary"
                  onClick={() => createMutation.mutate()}
                  disabled={createMutation.isPending}
                  aria-label="Create note"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </CardHeader>
              <CardContent>
                <div className="max-h-[calc(100vh-180px)] space-y-2 overflow-auto">
                  {notes.map((note) => {
                    const active = note.id === selectedId;
                    return (
                      <button
                        key={note.id}
                        type="button"
                        className={cn(
                          "w-full rounded-lg border px-3 py-3 text-left transition-colors",
                          active
                            ? "border-white/20 bg-white/[0.08]"
                            : "border-white/10 bg-transparent hover:border-white/20 hover:bg-white/[0.03]",
                        )}
                        onClick={() => setSelectedId(note.id)}
                      >
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 shrink-0 text-neutral-500" />
                          <div className="truncate text-sm font-light text-white">{note.title}</div>
                        </div>
                        <div className="font-jetbrains mt-2 flex items-center justify-between gap-3 text-xs font-light text-neutral-500">
                          <span>{note.word_count} words</span>
                          <StatusPill status={note.status} />
                        </div>
                      </button>
                    );
                  })}
                  {!notes.length && !notesQuery.isLoading ? (
                    <div className="font-jetbrains rounded-lg border border-white/10 px-3 py-4 text-xs font-light leading-5 text-neutral-500">
                      Create a note. Saved text is indexed into memory after autosave.
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </div>
        </aside>

        <section className="flex min-h-[calc(100vh-48px)] flex-col rounded-xl border border-white/10 bg-white/[0.015]">
          <header className="flex flex-col gap-4 border-b border-white/10 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-normal tracking-normal text-white">Notes</h1>
              <div className="font-jetbrains mt-1 text-xs font-light text-neutral-500">
                {selectedNote ? `note ${selectedNote.id}` : "select or create a note"}
              </div>
            </div>
            <div className="flex h-9 flex-nowrap items-center justify-end gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => createMutation.mutate()}
                disabled={createMutation.isPending}
                className="font-normal xl:hidden"
              >
                <Plus className="h-4 w-4" />
                New
              </Button>
              {selectedListItem ? (
                <span className="inline-flex h-9 items-center">
                  <StatusPill status={selectedListItem.status} />
                </span>
              ) : null}
              <span className="font-jetbrains inline-flex h-9 items-center text-xs font-light text-neutral-500">{saveState}</span>
              <Button
                variant="ghost"
                size="icon"
                className="text-neutral-600 hover:text-red-400"
                onClick={() => {
                  if (selectedId) deleteMutation.mutate(selectedId);
                }}
                disabled={!selectedId || deleteMutation.isPending}
                aria-label="Delete note"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          </header>

          <div className="flex-1 overflow-auto px-5 py-8">
            {selectedId ? (
              <div className="relative mx-auto flex min-h-full max-w-4xl flex-col">
                <input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="Untitled"
                  className="w-full bg-transparent text-3xl font-light tracking-normal text-white outline-none placeholder:text-neutral-800"
                />
                <textarea
                  ref={textareaRef}
                  value={content}
                  onChange={onContentChange}
                  onKeyDown={onContentKeyDown}
                  placeholder="Write your thoughts..."
                  spellCheck
                  className="mt-10 min-h-[62vh] w-full resize-none bg-transparent text-base font-light leading-8 text-neutral-100 outline-none placeholder:text-neutral-700"
                />
                <input
                  ref={imageInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    event.target.value = "";
                    if (file) imageUploadMutation.mutate(file);
                  }}
                />
                {slashRange ? (
                  <div className="absolute left-0 top-36 z-20 w-80 rounded-xl border border-white/10 bg-black/95 p-2 shadow-[0_24px_80px_rgba(0,0,0,0.55)]">
                    {filteredSlashCommands.length ? (
                      filteredSlashCommands.map((command, index) => {
                        const Icon = command.icon;
                        return (
                          <button
                            key={command.id}
                            type="button"
                            className={cn(
                              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                              index === slashIndex ? "bg-white/[0.12] text-white" : "text-neutral-400 hover:bg-white/[0.06] hover:text-white",
                            )}
                            onMouseDown={(event) => {
                              event.preventDefault();
                              runSlashCommand(command);
                            }}
                          >
                            <span className="font-jetbrains w-8 shrink-0 text-xs font-light text-neutral-500">{command.shortcut}</span>
                            <Icon className="h-4 w-4 shrink-0" />
                            <span className="text-sm font-light">{command.label}</span>
                          </button>
                        );
                      })
                    ) : (
                      <div className="font-jetbrains px-3 py-2 text-xs font-light text-neutral-600">No commands found.</div>
                    )}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mx-auto flex min-h-full max-w-2xl flex-col items-center justify-center py-24 text-center">
                <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
                  <FileText className="h-4 w-4 text-neutral-300" />
                </div>
                <h2 className="text-4xl font-light tracking-normal text-white">Write into memory.</h2>
                <p className="font-jetbrains mt-4 max-w-xl text-sm font-light leading-6 text-neutral-500">
                  Create plain text notes. Cortex autosaves them, indexes them, and makes them available in chat retrieval.
                </p>
                <Button className="mt-8 font-normal" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                  <Plus className="h-4 w-4" />
                  Create note
                </Button>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
