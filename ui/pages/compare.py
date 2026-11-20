import threading
from tkinter import ttk
import customtkinter as ctk
import requests
from ui.pages.compare_dialog import PriceCompareDialog

API = "http://localhost:8000"

class ComparePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        self.item_titles = {}

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        ctk.CTkLabel(header, text="Global Price Comparison", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        self.refresh_btn = ctk.CTkButton(header, text="Refresh Data", fg_color="#1f538d", hover_color="#14375e", command=self.fetch_data)
        self.refresh_btn.pack(side="right")

        self.status = ctk.CTkLabel(self, text="Finding items that exist on multiple platforms...", text_color="gray")
        self.status.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self._apply_tree_style()
        self.tree = ttk.Treeview(table_frame, style="Scrapa.Treeview", show="headings", selectmode="browse")
        self.tree.bind("<Double-1>", self._on_double_click)
        
        sb = ctk.CTkScrollbar(table_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)

        cols = [
            ("title", "Product Name", 350, "w"), 
            ("platforms", "Platforms Found", 200, "center"), 
            ("lowest", "Lowest Price", 100, "center"),
            ("average", "Average Price", 100, "center"),
            ("count", "Matches", 80, "center")
        ]
        self.tree.configure(columns=tuple(c[0] for c in cols), displaycolumns=tuple(c[0] for c in cols))
        for cid, text, width, anchor in cols:
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=width, anchor=anchor, stretch=(cid == "title"))

    def fetch_data(self):
        self.refresh_btn.configure(state="disabled", text="Loading...")
        self.status.configure(text="Clustering data across platforms...", text_color="gray")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            resp = requests.get(f"{API}/compare", timeout=30)
            resp.raise_for_status()
            self.app.submit_result(self._render_table, resp.json())
        except Exception as e:
            self.app.submit_result(self._render_error, str(e))

    def _render_table(self, data):
        self.refresh_btn.configure(state="normal", text="Refresh Data")
        self.tree.delete(*self.tree.get_children())
        self.item_titles.clear()

        if not data:
            self.status.configure(text="No matching items found across multiple platforms. Try scraping more data.", text_color="orange")
            return
            
        self.status.configure(text=f"Showing {len(data)} cross-platform matches.", text_color="#2ca02c")
        for i, row in enumerate(data):
            title_short = row.get('title', '')[:55] + "..." if len(row.get('title', '')) > 55 else row.get('title', '')
            tag = "odd" if i % 2 else "even"
            
            item_id = self.tree.insert("", "end", values=(
                title_short, 
                row.get("platforms", ""), 
                f"${row.get('lowest', 0):,.2f}", 
                f"${row.get('average', 0):,.2f}",
                row.get("count", 0)
            ), tags=(tag,))
            # Store full title for the dialog
            self.item_titles[item_id] = row.get("title")

    def _on_double_click(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        
        # Get full title from stored dict
        title = self.item_titles.get(item_id)
        
        # Fallback: try the displayed value (might have ...)
        if not title:
            vals = self.tree.item(item_id, "values")
            title = vals[0] if vals else None
            
        if title:
            PriceCompareDialog(self, title, self.app)

    def _render_error(self, msg):
        self.refresh_btn.configure(state="normal", text="Refresh Data")
        self.status.configure(text=f"Error: {msg}", text_color="red")

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
