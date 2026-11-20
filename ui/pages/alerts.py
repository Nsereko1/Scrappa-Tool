import customtkinter as ctk
import requests
import threading
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class AlertsPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Header
        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="ew")
        ctk.CTkLabel(header, text="🚨 Competitor Alerts & Price Trends", font=ctk.CTkFont(size=22, weight="bold"), text_color="#c62828").pack(side="left")
        self.refresh_btn = ctk.CTkButton(header, text="Refresh", command=self.fetch_data)
        self.refresh_btn.pack(side="right")

        # Chart Area
        self.chart_frame = ctk.CTkFrame(self)
        self.chart_frame.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")
        
        self.fig = Figure(figsize=(8, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.get_tk_widget().pack(expand=True, fill="both", padx=10, pady=10)

        # Alerts List
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")

    def fetch_data(self):
        self.refresh_btn.configure(state="disabled", text="Loading...")
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        try:
            alerts_resp = requests.get("http://localhost:8000/alerts", timeout=10)
            trends_resp = requests.get("http://localhost:8000/trends", timeout=10)
            alerts_resp.raise_for_status()
            trends_resp.raise_for_status()
            self.app.submit_result(self._render, (alerts_resp.json(), trends_resp.json()))
        except Exception as e:
            self.app.submit_result(self._error, str(e))

    def _error(self, msg):
        self.refresh_btn.configure(state="normal", text="Refresh")
        for child in self.scroll.winfo_children(): child.destroy()
        ctk.CTkLabel(self.scroll, text=f"Error: {msg}", text_color="red").pack(pady=20)

    def _render(self, data):
        alerts, trends = data
        self.refresh_btn.configure(state="normal", text="Refresh")
        self._draw_chart(trends)
        self._draw_alerts(alerts)

    def _draw_chart(self, trends):
        self.ax.clear()
        if not trends:
            self.ax.text(0.5, 0.5, "No trend data yet. Run multiple scrapes to see movement.", 
                         ha='center', va='center', transform=self.ax.transAxes)
        else:
            platforms = {}
            for row in trends:
                p = row['platform'].capitalize()
                if p not in platforms:
                    platforms[p] = {"dates": [], "prices": []}
                platforms[p]["dates"].append(row['snapshot_date'])
                platforms[p]["prices"].append(row['avg_price'])

            is_dark = ctk.get_appearance_mode() == "Dark"
            bg_color = "#2b2b2b" if is_dark else "#ffffff"
            text_color = "white" if is_dark else "black"
            self.fig.patch.set_facecolor(bg_color)
            self.ax.set_facecolor(bg_color)

            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
            
            for i, (p, d) in enumerate(platforms.items()):
                self.ax.plot(d["dates"], d["prices"], marker='o', label=p, color=colors[i % len(colors)], linewidth=2)

            self.ax.set_title("Average Price Trend by Platform (Up/Down)", color=text_color)
            self.ax.tick_params(colors=text_color)
            self.ax.set_ylabel("Avg Price", color=text_color)
            
            legend = self.ax.legend()
            for text in legend.get_texts():
                text.set_color(text_color)

        self.fig.tight_layout()
        self.canvas.draw()

    def _draw_alerts(self, alerts):
        for child in self.scroll.winfo_children(): child.destroy()

        if not alerts:
            ctk.CTkLabel(self.scroll, text="No alerts yet. Run a scrape twice to see price drops.").pack(pady=20)
            return

        for a in alerts:
            card = ctk.CTkFrame(self.scroll, fg_color=("gray85", "gray20"))
            card.pack(fill="x", padx=10, pady=5)
            ctk.CTkLabel(card, text=f"[{a['platform'].upper()}] {a['title'][:60]}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 2))
            color = "#2ca02c" if "drop" in a['message'].lower() else "white"
            ctk.CTkLabel(card, text=a['message'], text_color=color).pack(anchor="w", padx=10, pady=(0, 10))
