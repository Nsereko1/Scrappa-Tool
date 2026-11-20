import queue
import traceback
import customtkinter as ctk

from ui.pages.products import ProductsPage
from ui.pages.charts import ChartsPage
from ui.pages.alerts import AlertsPage
from ui.pages.compare import ComparePage
from ui.pages.discovery import DiscoveryPage

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")
PLATFORM_KEYS = ("jumia", "amazon", "alibaba", "ebay", "kibuga")

class BestSellerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Best-Seller Intelligence")
        self.geometry("1300x850")
        self.minsize(1100, 700)
        self.result_queue = queue.Queue()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.sidebar, text="Best-Seller\nIntel", font=ctk.CTkFont(size=22, weight="bold")).pack(padx=20, pady=(24, 20))

        self.nav_buttons = {}
        self._add_nav_button("products", "All Products")
        
        ctk.CTkLabel(self.sidebar, text="Filter by Brand", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").pack(padx=20, pady=(10, 0), anchor="w")
        self._add_nav_button("jumia", "Jumia", indent=True)
        self._add_nav_button("amazon", "Amazon", indent=True)
        self._add_nav_button("alibaba", "Alibaba", indent=True)
        self._add_nav_button("ebay", "eBay", indent=True)
        self._add_nav_button("kibuga", "Kibuga", indent=True)
        
        ctk.CTkLabel(self.sidebar, text="").pack(pady=10)
        self._add_nav_button("discovery", "Discovery Scanner")
        self._add_nav_button("compare", "Price Matrix")
        self._add_nav_button("charts", "Visualizations")
        self._add_nav_button("alerts", "Competitor Alerts")

        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {
            "products": ProductsPage(self.content, self),
            "charts": ChartsPage(self.content, self),
            "alerts": AlertsPage(self.content, self),
            "compare": ComparePage(self.content, self),
            "discovery": DiscoveryPage(self.content, self)
        }
        self._current_page = None
        self.nav_action("products") 
        self.after(50, self._drain_queue)

    def _add_nav_button(self, key, text, indent=False):
        pad_x = (30, 16) if indent else 16
        btn = ctk.CTkButton(self.sidebar, text=text, anchor="w", height=32, fg_color="transparent", hover_color=("gray60", "gray40"), command=lambda k=key: self.nav_action(k))
        btn.pack(fill="x", padx=pad_x, pady=2)
        self.nav_buttons[key] = btn

    def _show_page(self, name):
        if self._current_page == name: return
        if self._current_page: self.pages[self._current_page].grid_remove()
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        self._current_page = name

    def nav_action(self, key):
        if key in PLATFORM_KEYS:
            self._show_page("products")
            self.pages["products"].set_platform_filter(key.capitalize())
        elif key == "products":
            self._show_page("products")
            self.pages["products"].set_platform_filter("All")
        else:
            self._show_page(key)
            if key == "charts": self.pages["charts"].fetch_analytics()
            elif key == "alerts": self.pages["alerts"].fetch_data()
            elif key == "compare": self.pages["compare"].fetch_data()
            elif key == "discovery": self.pages["discovery"].fetch_data()
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=("gray75", "gray25") if k == key else "transparent")

    def _drain_queue(self):
        try:
            for _ in range(50):
                callback, payload = self.result_queue.get_nowait()
                try: callback(payload)
                except Exception: traceback.print_exc()
        except queue.Empty: pass
        finally: self.after(50, self._drain_queue)

    def submit_result(self, callback, payload):
        self.result_queue.put((callback, payload))

if __name__ == "__main__":
    app = BestSellerApp()
    app.mainloop()
