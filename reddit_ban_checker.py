"""
Reddit Ban Checker - GUI
Checks whether Reddit accounts are active, suspended, or missing
(deleted / shadowbanned) without opening a browser.

Uses only the Python standard library (tkinter + urllib). No installs needed.
"""

import csv
import json
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

USER_AGENT = "python:reddit-ban-checker:v1.0 (personal account status tool)"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

STATUS_ACTIVE = "Active"
STATUS_SUSPENDED = "Suspended (banned)"
STATUS_NOT_FOUND = "Not found / shadowbanned / deleted"
STATUS_INVALID = "Invalid username"
STATUS_ERROR = "Error"


def clean_username(raw):
    name = raw.strip()
    # Accept "u/name", "/u/name" or full profile URLs too
    name = re.sub(r"^(https?://)?(www\.|old\.)?reddit\.com/(user|u)/", "", name)
    name = re.sub(r"^/?u/", "", name).strip("/ ")
    return name if USERNAME_RE.match(name) else None


def check_username(username, retries=2):
    """Return (status, detail) for one username."""
    url = f"https://www.reddit.com/user/{quote(username)}/about.json"
    req = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(retries + 1):
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8")).get("data", {})
            if data.get("is_suspended"):
                return STATUS_SUSPENDED, "Account is suspended by Reddit"
            karma = data.get("total_karma", data.get("link_karma", 0) + data.get("comment_karma", 0))
            created = data.get("created_utc")
            age = ""
            if created:
                age = time.strftime("%Y-%m-%d", time.gmtime(created))
            return STATUS_ACTIVE, f"Karma: {karma}" + (f" | Created: {age}" if age else "")
        except HTTPError as e:
            if e.code == 404:
                return STATUS_NOT_FOUND, "Profile doesn't exist publicly"
            if e.code == 429 and attempt < retries:
                time.sleep(10 * (attempt + 1))  # rate limited: back off and retry
                continue
            if e.code == 403:
                return STATUS_ERROR, "403 Forbidden - Reddit blocked the request (try a longer delay or later)"
            return STATUS_ERROR, f"HTTP {e.code}"
        except URLError as e:
            return STATUS_ERROR, f"Network error: {e.reason}"
        except (json.JSONDecodeError, ValueError):
            return STATUS_ERROR, "Unexpected response from Reddit"
        except Exception as e:
            return STATUS_ERROR, str(e)
    return STATUS_ERROR, "Rate limited - try a longer delay"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Reddit Ban Checker")
        self.geometry("820x560")
        self.minsize(640, 420)
        self.stop_flag = threading.Event()
        self.worker = None
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Usernames (one per line, u/name or profile links also work):").pack(anchor="w")

        self.input_box = tk.Text(top, height=7, wrap="none", font=("Consolas", 10))
        self.input_box.pack(fill="x", pady=(2, 4))

        controls = ttk.Frame(self)
        controls.pack(fill="x", **pad)

        ttk.Button(controls, text="Load file…", command=self.load_file).pack(side="left")
        ttk.Label(controls, text="  Delay (s):").pack(side="left")
        self.delay_var = tk.StringVar(value="2")
        ttk.Spinbox(controls, from_=0.5, to=60, increment=0.5, width=6,
                    textvariable=self.delay_var).pack(side="left")

        self.start_btn = ttk.Button(controls, text="Check", command=self.start)
        self.start_btn.pack(side="left", padx=(12, 4))
        self.stop_btn = ttk.Button(controls, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(controls, text="Export CSV…", command=self.export_csv).pack(side="right")
        ttk.Button(controls, text="Clear", command=self.clear_results).pack(side="right", padx=4)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", **pad)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, **pad)
        cols = ("username", "status", "detail")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        for col, w in zip(cols, (160, 230, 380)):
            self.tree.heading(col, text=col.capitalize())
            self.tree.column(col, width=w, anchor="w")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.tag_configure("active", foreground="#1a7f37")
        self.tree.tag_configure("suspended", foreground="#cf222e")
        self.tree.tag_configure("notfound", foreground="#bc4c00")
        self.tree.tag_configure("error", foreground="#6e7781")

        self.summary_var = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.summary_var, anchor="w").pack(fill="x", padx=8, pady=(0, 8))

    # ---------- Actions ----------
    def load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                self.input_box.delete("1.0", "end")
                self.input_box.insert("1.0", f.read())
        except Exception as e:
            messagebox.showerror("Error", f"Couldn't read file:\n{e}")

    def start(self):
        lines = [l for l in self.input_box.get("1.0", "end").splitlines() if l.strip()]
        if not lines:
            messagebox.showinfo("Nothing to check", "Enter or load at least one username.")
            return
        try:
            delay = max(0.5, min(60.0, float(self.delay_var.get())))
        except ValueError:
            delay = 2.0

        # de-duplicate while keeping order
        seen, names = set(), []
        for l in lines:
            key = l.strip().lower()
            if key not in seen:
                seen.add(key)
                names.append(l.strip())

        self.clear_results()
        self.progress.configure(maximum=len(names), value=0)
        self.stop_flag.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.counts = {"active": 0, "suspended": 0, "notfound": 0, "error": 0}

        self.worker = threading.Thread(target=self._run, args=(names, delay), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_flag.set()
        self.summary_var.set("Stopping…")

    def _run(self, names, delay):
        for i, raw in enumerate(names):
            if self.stop_flag.is_set():
                break
            name = clean_username(raw)
            if not name:
                result = (raw, STATUS_INVALID, "3-20 chars: letters, numbers, _ or -", "error")
            else:
                self.after(0, self.summary_var.set, f"Checking {name} ({i + 1}/{len(names)})…")
                status, detail = check_username(name)
                tag = {STATUS_ACTIVE: "active", STATUS_SUSPENDED: "suspended",
                       STATUS_NOT_FOUND: "notfound"}.get(status, "error")
                result = (name, status, detail, tag)
            self.after(0, self._add_row, result)
            if i < len(names) - 1 and name:
                # sleep in small steps so Stop responds quickly
                end = time.time() + delay
                while time.time() < end and not self.stop_flag.is_set():
                    time.sleep(0.1)
        self.after(0, self._done)

    def _add_row(self, result):
        name, status, detail, tag = result
        self.tree.insert("", "end", values=(name, status, detail), tags=(tag,))
        self.counts[tag] += 1
        self.progress.step(1)
        self._update_summary()

    def _update_summary(self, prefix=""):
        c = self.counts
        self.summary_var.set(
            f"{prefix}Active: {c['active']}   Suspended: {c['suspended']}   "
            f"Not found/shadowbanned: {c['notfound']}   Errors/invalid: {c['error']}"
        )

    def _done(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._update_summary("Stopped. " if self.stop_flag.is_set() else "Done. ")

    def clear_results(self):
        self.tree.delete(*self.tree.get_children())
        self.progress.configure(value=0)
        self.summary_var.set("Ready")

    def export_csv(self):
        rows = [self.tree.item(i, "values") for i in self.tree.get_children()]
        if not rows:
            messagebox.showinfo("Nothing to export", "Run a check first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")],
                                            initialfile="reddit_results.csv")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["username", "status", "detail"])
            w.writerows(rows)
        messagebox.showinfo("Saved", f"Results saved to:\n{path}")


if __name__ == "__main__":
    App().mainloop()
