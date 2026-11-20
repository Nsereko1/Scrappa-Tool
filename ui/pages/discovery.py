import threading
import datetime
from tkinter import ttk
import customtkinter as ctk
import requests

API = "http://localhost:8000"

class DiscoveryPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.next_run_time = None
        self.view_mode = "summary"

        # 1. Header Row
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        self.title_label = ctk.CTkLabel(header, text="Autonomous Discovery Tracker", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        
        self.back_btn = ctk.CTkButton(header, text="<- Back to Summary", fg_color="gray30", hover_color="gray40", command=self.show_summary, width=140)
        
        self.refresh_btn = ctk.CTkButton(header, text="Refresh", fg_color="#1f538d", hover_color="#14375e", command=self.fetch_data, width=80)
        self.refresh_btn.pack(side="right", padx=5)
        
        self.force_btn = ctk.CTkButton(header, text="Force Scan", fg_color="#c62828", hover_color="#b71c1c", command=self.force_scan, width=100)
        self.force_btn.pack(side="right", padx=5)

        # 2. Status & Timer Row
        status_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray20"), corner_radius=8)
        status_frame.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")
        self.status_label = ctk.CTkLabel(status_frame, text="Fetching agent status...", font=ctk.CTkFont(weight="bold"))
        self.status_label.pack(side="left", padx=15, pady=10)
        self.timer_label = ctk.CTkLabel(status_frame, text="", font=ctk.CTkFont(weight="bold"), text_color="#1f538d")
        self.timer_label.pack(side="right", padx=15, pady=10)

        # 3. Brand Totals Row
        self.brands_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.brands_frame.grid(row=2, column=0, padx=16, pady=(0, 8), sticky="ew")
        
        self.table_title = ctk.CTkLabel(self, text="Recent Background Activity:", font=ctk.CTkFont(size=14, weight="bold"), text_color="gray")
        self.table_title.grid(row=3, column=0, padx=20, pady=(5, 0), sticky="w")

        # 4. Table Frame
        self.table_frame = ctk.CTkFrame(self)
        self.table_frame.grid(row=4, column=0, padx=16, pady=(8, 16), sticky="nsew")
        self.table_frame.grid_columnconfigure(0, weight=1)
        self.table_frame.grid_rowconfigure(0, weight=1)

        self._apply_tree_style()
        self.tree = None
        self._build_table(["Timestamp", "Platform", "New Items", "Total Scanned"])

        self.fetch_data()
        self._tick_timer()

    def _build_table(self, headers):
        if self.tree:
            self.tree.destroy()
        if hasattr(self, "sb"):
            self.sb.destroy()

        self.tree = ttk.Treeview(self.table_frame, style="Scrapa.Treeview", show="headings", selectmode="browse")
        self.tree.bind("<Double-1>", self._on_row_click)
        
        self.sb = ctk.CTkScrollbar(self.table_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        self.sb.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)

        cols = [f"col{i}" for i in range(len(headers))]
        self.tree.configure(columns=cols, displaycolumns=cols)
        
        for i, h in enumerate(headers):
            self.tree.heading(cols[i], text=h)
            self.tree.column(cols[i], width=200, anchor="center")

    def fetch_data(self):
        if self.view_mode == "summary":
            threading.Thread(target=self._fetch_summary_worker, daemon=True).start()

    def _fetch_summary_worker(self):
        try:
            ledger_data = requests.get(f"{API}/tracker_history", timeout=10).json()
            stats_data = requests.get(f"{API}/analytics", timeout=10).json()
            self.app.submit_result(self._render_summary, (ledger_data, stats_data))
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_summary(self, payload):
        ledger_data, stats_data = payload
        
        for widget in self.brands_frame.winfo_children(): 
            widget.destroy()

        # --- FIX: Force all 5 brands to show ---
        found_counts = {p["platform"].lower(): p["count"] for p in stats_data.get("platforms", [])}
        
        for plat in ["jumia", "amazon", "alibaba", "ebay", "kibuga"]:
            count = found_counts.get(plat, 0)
            box = ctk.CTkButton(
                self.brands_frame, 
                text=f"{plat.upper()}\n{count:,}", 
                font=ctk.CTkFont(weight="bold", size=13), 
                fg_color="#1f538d", 
                hover_color="#14375e", 
                width=100, 
                height=50,
                command=lambda p=plat: self.load_details(platform=p)
            )
            box.pack(side="left", padx=5)

        self._build_table(["Timestamp", "Platform", "New Items", "Total Scanned"])
        
        for i, row in enumerate(ledger_data):
            ts = row.get("timestamp", "")[:19]
            tag = "odd" if i % 2 else "even"
            self.tree.insert("", "end", values=(ts[:16], row.get("platform", "").upper(), f"+{row.get('new_items', 0)}", row.get("total_scanned", 0)), tags=(tag,))

    def _on_row_click(self, event):
        if self.view_mode != "summary": return
        item = self.tree.focus()
        if not item: return
        vals = self.tree.item(item, "values")
        if not vals: return
        timestamp = vals[0]
        self.load_details(timestamp=timestamp)

    def load_details(self, platform=None, timestamp=None):
        self.view_mode = "details"
        self.title_label.configure(text="Items Added in this Scan" if timestamp else f"New {platform.upper()} Items")
        self.table_title.configure(text="Recently Added Items:")
        
        self.refresh_btn.pack_forget()
        self.force_btn.pack_forget()
        self.back_btn.pack(side="right", padx=5)
        
        threading.Thread(target=self._fetch_details_worker, args=(platform, timestamp), daemon=True).start()

    def _fetch_details_worker(self, platform, timestamp):
        try:
            params = {}
            if timestamp: params["timestamp"] = timestamp
            if platform: params["platform"] = platform
            
            resp = requests.get(f"{API}/tracker_details", params=params, timeout=10)
            self.app.submit_result(self._render_details, resp.json())
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_details(self, data):
        self._build_table(["Product Name", "Price (USD)", "Date Added"])
        
        for i, row in enumerate(data):
            tag = "odd" if i % 2 else "even"
            price = f"${row['price_usd']:,.2f}" if row['price_usd'] else "N/A"
            title = row['title'][:60] + "..." if len(row['title']) > 60 else row['title']
            self.tree.insert("", "end", values=(title, price, row['last_seen']), tags=(tag,))
            
        if not data:
            self.tree.insert("", "end", values=("No items found in this scan.", "", ""))

    def show_summary(self):
        self.view_mode = "summary"
        self.title_label.configure(text="Autonomous Discovery Tracker")
        self.table_title.configure(text="Recent Background Activity:")
        
        self.back_btn.pack_forget()
        self.refresh_btn.pack(side="right", padx=5)
        self.force_btn.pack(side="right", padx=5)
        
        self.fetch_data()

    def _render_error(self, msg):
        self.status_label.configure(text=f"Error: {msg}", text_color="red")

    def _tick_timer(self):
        try:
            status = requests.get(f"{API}/agent_status", timeout=3).json()
            state = status.get("status", "Idle")
            next_run = status.get("next_run")
            last_run = status.get("last_run")
            
            if state == "Scanning live site...":
                self.status_label.configure(text="Status: ACTIVELY SCANNING...", text_color="#2ca02c")
                self.timer_label.configure(text="Please wait...", text_color="#2ca02c")
                self.next_run_time = None
            elif next_run:
                self.status_label.configure(text=f"Last Scan: {last_run[11:19] if last_run else 'N/A'}", text_color="white")
                self.next_run_time = datetime.datetime.fromisoformat(next_run)
            else:
                self.status_label.configure(text="Status: Initializing...", text_color="gray")
        except Exception:
            self.status_label.configure(text="Status: Offline", text_color="red")

        if self.next_run_time:
            diff = self.next_run_time - datetime.datetime.now()
            if diff.total_seconds() <= 0:
                self.timer_label.configure(text="Next scan: Starting soon...", text_color="#ef6c00")
            else:
                mins, secs = divmod(int(diff.total_seconds()), 60)
                self.timer_label.configure(text=f"Next scan in: {mins}m {secs}s", text_color="#1f538d")

        self.after(1000, self._tick_timer)

    def force_scan(self):
        self.force_btn.configure(state="disabled", text="Scanning...")
        def _worker():
            try:
                requests.post(f"{API}/force_scan", timeout=10)
                self.after(3000, lambda: self.force_btn.configure(state="normal", text="Force Scan"))
            except Exception:
                self.after(3000, lambda: self.force_btn.configure(state="normal", text="Force Scan"))
        threading.Thread(target=_worker, daemon=True).start()

    def _apply_tree_style(self):
        dark = ctk.get_appearance_mode() == "Dark"
        bg, fg = ("#2b2b2b", "#dce4ee") if dark else ("#ffffff", "#1a1a1a")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Scrapa.Treeview", background=bg, fieldbackground=bg, foreground=fg, rowheight=32, borderwidth=0, font=("Helvetica", 12))
        style.configure("Scrapa.Treeview.Heading", background="#1f538d", foreground="white", relief="flat", font=("Helvetica", 12, "bold"))
        style.map("Scrapa.Treeview", background=[("selected", "#1f538d")], foreground=[("selected", "white")])
        if hasattr(self, "tree"):
            self.tree.tag_configure("odd", background="#333333" if dark else "#f2f5fa")
            self.tree.tag_configure("even", background=bg)