# ui/pages/snapshots.py
import threading, datetime, requests
import customtkinter as ctk
from tkinter import messagebox

class SnapshotsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Snapshot Explorer",
                     font=ctk.CTkFont(size=22, weight="bold")
                     ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        ctrl = ctk.CTkFrame(self)
        ctrl.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        ctrl.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(ctrl, text="Snapshot date").grid(row=0, column=0, padx=(12, 6))
        self.date_entry = ctk.CTkEntry(ctrl, placeholder_text="YYYY-MM-DD")
        self.date_entry.insert(0, datetime.date.today().isoformat())
        self.date_entry.grid(row=0, column=1, padx=(0, 12), sticky="ew")

        self.load_btn = ctk.CTkButton(ctrl, text="Load snapshot", command=self.load_snapshot)
        self.load_btn.grid(row=0, column=2, padx=6)
        self.refresh_btn = ctk.CTkButton(
            ctrl, text="Trigger collection run", fg_color="gray30",
            command=self.trigger_run,
        )
        self.refresh_btn.grid(row=0, column=3, padx=(6, 12))

        self.summary = ctk.CTkLabel(self, text="No snapshot loaded.", anchor="w")
        self.summary.grid(row=2, column=0, padx=24, pady=(4, 12), sticky="ew")

    def load_snapshot(self):
        date = self.date_entry.get().strip()
        self.load_btn.configure(state="disabled", text="Loading…")

        def worker():
            try:
                resp = requests.get(
                    "http://localhost:8000/bestsellers",
                    params={"snapshot_date": date}, timeout=15,
                )
                resp.raise_for_status()
                rows = resp.json()
                self.app.submit_result(self._render, rows)
            except Exception as exc:
                self.app.submit_result(self._render_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _render(self, rows):
        self.load_btn.configure(state="normal", text="Load snapshot")
        if not rows:
            self.summary.configure(text="No records for that date.")
            return
        platforms = {r["platform"] for r in rows}
        high_conf = sum(1 for r in rows if r.get("confidence") == "high")
        self.summary.configure(
            text=f"{len(rows)} records across {len(platforms)} platform(s) · "
                 f"{high_conf} high-confidence"
        )
        # Hand the data to the Products page so the user can inspect immediately
        self.app.pages["products"].set_data(rows)

    def _render_error(self, message):
        self.load_btn.configure(state="normal", text="Load snapshot")
        messagebox.showerror("Snapshot load failed", message[:300])

    def trigger_run(self):
        self.refresh_btn.configure(state="disabled", text="Running…")

        def worker():
            try:
                requests.post("http://localhost:8000/run", timeout=300)
                self.app.submit_result(self._run_done, "Collection finished.")
            except Exception as exc:
                self.app.submit_result(self._run_error, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _run_done(self, msg):
        self.refresh_btn.configure(state="normal", text="Trigger collection run")
        messagebox.showinfo("Run complete", msg)

    def _run_error(self, msg):
        self.refresh_btn.configure(state="normal", text="Trigger collection run")
        messagebox.showerror("Run failed", msg[:300])