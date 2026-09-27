"""A read-only mailbox the tester explores with tools.

Emails get handles (e1, e2, ...) and threads too (t1, t2, ...), so the model cites them reliably and
nothing in a handle says which emails are planted. Every tool call is logged, so a run can report
tool calls, emails read, and how many planted threads the agent opened.
"""
from __future__ import annotations

from src.tester.retrieval import BM25, tokenize


def _text(m: dict) -> str:
    return (m.get("subject", "") or "") + " " + (m.get("body", "") or "")


def _line(s: str, n: int) -> str:
    return " ".join((s or "").split())[:n]


class MailboxEnv:
    def __init__(self, threads: list[list[dict]], planted_ids: set[str]):
        self.msgs: dict[str, dict] = {}
        self.thread_of: dict[str, str] = {}
        self.thread_msgs: dict[str, list[str]] = {}
        self.clue_handles: set[str] = set()
        self.log: list[dict] = []
        self.opened: set[str] = set()
        for ti, th in enumerate(threads, 1):
            th_h = f"t{ti}"
            self.thread_msgs[th_h] = []
            for m in th:
                h = f"e{len(self.msgs) + 1}"
                self.msgs[h] = m
                self.thread_of[h] = th_h
                self.thread_msgs[th_h].append(h)
                if m.get("id") in planted_ids:
                    self.clue_handles.add(h)
        self._handles = list(self.msgs)
        self._bm = BM25([tokenize(_text(self.msgs[h])) for h in self._handles])

    def _row(self, h: str) -> str:
        m = self.msgs[h]
        mark = "  [read]" if h in self.opened else ""
        return (f"{h} | {(m.get('date', '') or '')[:10]} | {_line(m.get('from', ''), 28)} "
                f"| {_line(m.get('subject', ''), 50)} | {_line(m.get('body', ''), 90)}{mark}")

    def search(self, query: str, k: int = 12) -> str:
        scores = self._bm.scores(tokenize(query or ""))
        order = sorted(range(len(self._handles)), key=lambda i: scores[i], reverse=True)[:k]
        hits = [self._handles[i] for i in order if scores[i] > 0]
        self.log.append({"tool": "SEARCH", "arg": query, "returned": hits})
        return "\n".join(self._row(h) for h in hits) if hits else "(no matches)"

    def expand(self, handle: str, k: int = 8, log: bool = True) -> str:
        """Other emails about the same matter: the email's own text as the query, read emails excluded."""
        h = (handle or "").strip().split()[0] if handle else ""
        m = self.msgs.get(h)
        if not m:
            if log:
                self.log.append({"tool": "EXPAND", "arg": h, "returned": []})
            return f"(no email with handle {h!r})"
        scores = self._bm.scores(tokenize(_text(m)))
        order = sorted(range(len(self._handles)), key=lambda i: scores[i], reverse=True)
        hits = [self._handles[i] for i in order
                if self._handles[i] != h and self._handles[i] not in self.opened and scores[i] > 0][:k]
        if log:
            self.log.append({"tool": "EXPAND", "arg": h, "returned": hits})
        return "\n".join(self._row(x) for x in hits) if hits else "(nothing related)"

    def read(self, handle: str) -> str:
        """The whole thread the handle belongs to."""
        h = (handle or "").strip().split()[0] if handle else ""
        th_h = h if h in self.thread_msgs else self.thread_of.get(h)
        mh = self.thread_msgs.get(th_h, [])
        self.log.append({"tool": "READ", "arg": h, "returned": list(mh)})
        self.opened.update(mh)
        if not mh:
            return f"(no email with handle {h!r})"
        # Evidence may occur at the end; only search snippets are truncated.
        out = [f"thread {th_h} ({len(mh)} message{'s' if len(mh) != 1 else ''}):"]
        for x in mh:
            m = self.msgs[x]
            out.append(f"\n[{x}] From: {m.get('from', '')}  Date: {(m.get('date', '') or '')[:10]}\n"
                       f"Subject: {m.get('subject', '')}\n{m.get('body', '') or ''}")
        return "\n".join(out)

    def list_threads(self, cap: int = 40) -> str:
        handles = list(self.thread_msgs)
        total = len(handles)
        if total > cap:
            step = total / cap
            handles = [handles[int(i * step)] for i in range(cap)]
        handles.sort(key=lambda th: (self.msgs[self.thread_msgs[th][0]].get("date", "") or ""))
        out = [f"{total} threads in this mailbox; here is a sample of {len(handles)}:"]
        for th_h in handles:
            mh = self.thread_msgs[th_h]
            m0 = self.msgs[mh[0]]
            out.append(f"{th_h} | {(m0.get('date', '') or '')[:10]} | {len(mh)} msg | {_line(m0.get('subject', ''), 60)}")
        self.log.append({"tool": "LIST", "arg": "", "returned": handles})
        return "\n".join(out)

    def metrics(self) -> dict:
        reads = [e for e in self.log if e["tool"] == "READ"]
        read_handles = [h for e in reads for h in e["returned"]]
        uniq = set(read_handles)
        clue_threads = {self.thread_of[c] for c in self.clue_handles}
        clue_read = {self.thread_of[c] for c in (self.clue_handles & uniq)}
        return {
            "n_tool_calls": len(self.log),
            "n_search": sum(1 for e in self.log if e["tool"] == "SEARCH"),
            "n_read": len(reads),
            "n_emails_opened": len(uniq),
            "n_threads_opened": len({self.thread_of[h] for h in uniq}),
            "n_redundant_reads": len(read_handles) - len(uniq),
            "n_clues_total": len(clue_threads),
            "n_clues_read": len(clue_read),
            "clue_recall": round(len(clue_read) / len(clue_threads), 3) if clue_threads else None,
        }

    def clue_precision_recall(self, cited: list[str]) -> tuple[float, float]:
        """Thread-level: cited handles are reduced to their threads; a planted thread counts once."""
        cited = [c for c in cited if c in self.msgs]
        if not cited:
            return 0.0, 0.0
        cited_threads = {self.thread_of[c] for c in cited}
        clue_threads = {self.thread_of[c] for c in self.clue_handles}
        hit = cited_threads & clue_threads
        return round(len(hit) / len(cited_threads), 3), round(len(hit) / max(1, len(clue_threads)), 3)
