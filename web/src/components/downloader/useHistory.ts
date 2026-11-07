"use client";

import { useCallback, useEffect, useState } from "react";

export type HistoryEntry = { url: string; title: string; platform: string; at: number };

const KEY = "cf:history:v1";
const MAX = 8;

function read(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
  } catch {
    return [];
  }
}

function write(list: HistoryEntry[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* private mode / storage blocked: history is a convenience only */
  }
}

/** Recent links, stored only in this browser. */
export function useHistory() {
  const [items, setItems] = useState<HistoryEntry[]>([]);

  useEffect(() => setItems(read()), []);

  const add = useCallback((e: Omit<HistoryEntry, "at">) => {
    setItems((prev) => {
      const next = [{ ...e, at: Date.now() }, ...prev.filter((p) => p.url !== e.url)].slice(0, MAX);
      write(next);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    write([]);
    setItems([]);
  }, []);

  return { items, add, clear };
}
