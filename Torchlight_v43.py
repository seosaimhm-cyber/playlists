import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import csv
import webbrowser
import urllib.parse
from collections import Counter
import json
from PIL import Image, ImageTk  # Added for logo display
import sys
import os
import threading
import yt_dlp

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)
	
# --- Define two separate database files ---
MASTER_DB_FILE = "staffordsongs.db"  # Your main database with music records
USER_PLAYLIST_DB_FILE = "user_playlists.db" # New database for user-created playlists

class MinimalPlaylistApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Playlist Archive Project")
        self.root.geometry("1400x800")

        self.conn_master = None  # Connection for master music data
        self.cursor_master = None
        self.conn_playlists = None # Connection for user playlists
        self.cursor_playlists = None

        # Initialize these attributes to None; they will be created in create_*_stats methods
        self.overview_text = None
        self.top_artists_tree = None
        self.top_labels_tree = None
        self.top_djs_tree = None
        self.details_text = None

        self.connect_dbs()
        self.init_playlist_tables()
        self.create_widgets()
        self.populate_dropdowns()
        self.load_data() # Loads from master_db initially

    def connect_dbs(self):
        try:
            # Connect to the master music database
            self.conn_master = sqlite3.connect(MASTER_DB_FILE)
            self.cursor_master = self.conn_master.cursor()

            # Connect to the user playlists database
            self.conn_playlists = sqlite3.connect(USER_PLAYLIST_DB_FILE)
            self.cursor_playlists = self.conn_playlists.cursor()

        except sqlite3.Error as e:
            messagebox.showerror("Database Connection Error", str(e))
            self.root.destroy()

    def init_playlist_tables(self):
        try:
            self.cursor_playlists.execute('''
                CREATE TABLE IF NOT EXISTS user_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.cursor_playlists.execute('''
                CREATE TABLE IF NOT EXISTS playlist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER,
                    artist TEXT,
                    title TEXT,
                    label TEXT,
                    dj TEXT,
                    club TEXT,
                    town TEXT,
                    country TEXT,
                    date TEXT,
                    position INTEGER,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (playlist_id) REFERENCES user_playlists(id) ON DELETE CASCADE
                )
            ''')
            self.conn_playlists.commit()
        except sqlite3.Error as e:
            messagebox.showerror("Playlist Database Error", str(e))

    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)

        self.search_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.search_frame, text="Search & Browse")

        self.playlist_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.playlist_frame, text="My Playlists")

        self.stats_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.stats_frame, text="Database Statistics")

        self.create_search_tab()
        self.create_playlist_tab()
        self.create_stats_tab()

    def create_search_tab(self):
        main_frame = ttk.Frame(self.search_frame, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.search_frame.columnconfigure(0, weight=1)
        self.search_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        search_frame = ttk.LabelFrame(main_frame, text="Search Filters", padding="10")
        search_frame.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0,10))

        results_frame = ttk.Frame(main_frame)
        results_frame.grid(row=0, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(1, weight=1)

        self.create_search_controls(search_frame)
        self.create_results_table(results_frame)

    def create_playlist_tab(self):
        main_frame = ttk.Frame(self.playlist_frame, padding="10")
        main_frame.pack(fill='both', expand=True)

        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill='both', expand=True)

        left_frame = ttk.LabelFrame(paned, text="Playlists", padding="10")
        right_frame = ttk.LabelFrame(paned, text="Playlist Contents", padding="10")

        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=2)

        self.create_playlist_list(left_frame)
        self.create_playlist_contents(right_frame)

    def create_playlist_list(self, parent):
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill='x', pady=(0,10))

        ttk.Button(btn_frame, text="New", command=self.create_playlist).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Rename", command=self.rename_playlist).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Delete", command=self.delete_playlist).pack(side='left')

        self.playlist_tree = ttk.Treeview(parent, columns=('Count', 'Created'), show='tree headings', height=15)
        self.playlist_tree.heading('#0', text='Playlist Name')
        self.playlist_tree.heading('Count', text='Tracks')
        self.playlist_tree.heading('Created', text='Created')
        self.playlist_tree.column('#0', width=200)
        self.playlist_tree.column('Count', width=60)
        self.playlist_tree.column('Created', width=100)

        playlist_scroll = ttk.Scrollbar(parent, orient='vertical', command=self.playlist_tree.yview)
        self.playlist_tree.configure(yscrollcommand=playlist_scroll.set)

        self.playlist_tree.pack(side='left', fill='both', expand=True)
        playlist_scroll.pack(side='right', fill='y')

        self.playlist_tree.bind('<<TreeviewSelect>>', self.on_playlist_select)

        self.load_playlists()

    def create_playlist_contents(self, parent):
        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0,10))

        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_from_playlist).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Download Selected", command=lambda: self.download_audio('playlist')).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Move Up", command=lambda: self.move_track(-1)).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Move Down", command=lambda: self.move_track(1)).pack(side='left', padx=(0,5))
        ttk.Button(btn_frame, text="Export CSV", command=self.export_playlist).pack(side='left')

        self.playlist_label = ttk.Label(parent, text="Select a playlist")
        self.playlist_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0,5))

        columns = ('Artist', 'Title', 'Label', 'DJ', 'Club', 'Town', 'Country', 'Date')
        self.playlist_contents_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)

        widths = {'Artist': 120, 'Title': 150, 'Label': 120, 'DJ': 100, 'Club': 100, 'Town': 80, 'Country': 80, 'Date': 80}
        for col in columns:
            self.playlist_contents_tree.heading(col, text=col)
            self.playlist_contents_tree.column(col, width=widths[col], minwidth=50)

        p_v_scroll = ttk.Scrollbar(parent, orient='vertical', command=self.playlist_contents_tree.yview)
        p_h_scroll = ttk.Scrollbar(parent, orient='horizontal', command=self.playlist_contents_tree.xview)
        self.playlist_contents_tree.configure(yscrollcommand=p_v_scroll.set, xscrollcommand=p_h_scroll.set)

        self.playlist_contents_tree.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        p_v_scroll.grid(row=2, column=1, sticky=(tk.N, tk.S))
        p_h_scroll.grid(row=3, column=0, sticky=(tk.W, tk.E))

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        self.playlist_contents_tree.bind('<Button-3>', self.show_playlist_context_menu)
        self.playlist_contents_tree.bind('<Double-1>', self.on_playlist_double_click)

        self.playlist_context_menu = tk.Menu(self.root, tearoff=0)
        self.playlist_context_menu.add_command(label="Search YouTube", command=lambda: self.open_playlist_link('youtube'))
        self.playlist_context_menu.add_command(label="Search Spotify", command=lambda: self.open_playlist_link('spotify'))
        self.playlist_context_menu.add_command(label="Search Discogs", command=lambda: self.open_playlist_link('discogs'))

    def create_stats_tab(self):
        stats_main = ttk.Frame(self.stats_frame, padding="10")
        stats_main.pack(fill='both', expand=True)

        title_label = ttk.Label(stats_main, text="Database Statistics", font=('TkDefaultFont', 14, 'bold'))
        title_label.pack(pady=(0, 20))

        stats_notebook = ttk.Notebook(stats_main)
        stats_notebook.pack(fill='both', expand=True)

        overview_frame = ttk.Frame(stats_notebook)
        stats_notebook.add(overview_frame, text="Overview")
        self.create_overview_stats(overview_frame)

        toplists_frame = ttk.Frame(stats_notebook)
        stats_notebook.add(toplists_frame, text="Top Lists")
        self.create_toplists_stats(toplists_frame)

        details_frame = ttk.Frame(stats_notebook)
        stats_notebook.add(details_frame, text="Detailed Breakdown")
        self.create_details_stats(details_frame)

        refresh_btn = ttk.Button(stats_main, text="Refresh Statistics", command=self.refresh_stats)
        refresh_btn.pack(pady=10)

    def create_overview_stats(self, parent):
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.overview_text = tk.Text(scrollable_frame, wrap=tk.WORD, height=25, width=80, font=('Consolas', 10))
        self.overview_text.pack(padx=10, pady=10, fill='both', expand=True)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_overview_stats()

    def create_toplists_stats(self, parent):
        container_frame = ttk.Frame(parent)
        container_frame.pack(fill='both', expand=True, pady=10, padx=5)

        container_frame.columnconfigure(0, weight=1)
        container_frame.columnconfigure(1, weight=1)
        container_frame.columnconfigure(2, weight=1)

        top_artists_frame = ttk.LabelFrame(container_frame, text="Most Frequent Artists", padding="10")
        top_artists_frame.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E), padx=(0,5))
        self.top_artists_tree = ttk.Treeview(top_artists_frame, columns=('Artist', 'Count'), show='headings', height=15)
        self.top_artists_tree.heading('Artist', text='Artist')
        self.top_artists_tree.heading('Count', text='Count')
        self.top_artists_tree.column('Artist', width=150, anchor='w')
        self.top_artists_tree.column('Count', width=60, anchor='e')
        self.top_artists_tree.pack(fill='both', expand=True)
        self.top_artists_tree.bind('<Double-1>', lambda e: self.on_toplist_double_click(e, 'Artist'))

        top_labels_frame = ttk.LabelFrame(container_frame, text="Most Frequent Labels", padding="10")
        top_labels_frame.grid(row=0, column=1, sticky=(tk.N, tk.S, tk.W, tk.E), padx=5)
        self.top_labels_tree = ttk.Treeview(top_labels_frame, columns=('Label', 'Count'), show='headings', height=15)
        self.top_labels_tree.heading('Label', text='Label')
        self.top_labels_tree.heading('Count', text='Count')
        self.top_labels_tree.column('Label', width=150, anchor='w')
        self.top_labels_tree.column('Count', width=60, anchor='e')
        self.top_labels_tree.pack(fill='both', expand=True)
        self.top_labels_tree.bind('<Double-1>', lambda e: self.on_toplist_double_click(e, 'Label'))

        top_djs_frame = ttk.LabelFrame(container_frame, text="Most Frequent DJs", padding="10")
        top_djs_frame.grid(row=0, column=2, sticky=(tk.N, tk.S, tk.W, tk.E), padx=(5,0))
        self.top_djs_tree = ttk.Treeview(top_djs_frame, columns=('DJ', 'Count'), show='headings', height=15)
        self.top_djs_tree.heading('DJ', text='DJ')
        self.top_djs_tree.heading('Count', text='Count')
        self.top_djs_tree.column('DJ', width=150, anchor='w')
        self.top_djs_tree.column('Count', width=60, anchor='e')
        self.top_djs_tree.pack(fill='both', expand=True)
        self.top_djs_tree.bind('<Double-1>', lambda e: self.on_toplist_double_click(e, 'DJ'))

        container_frame.rowconfigure(0, weight=1)

        self.load_toplists_stats()

    def create_details_stats(self, parent):
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        self.details_text = tk.Text(scrollable_frame, wrap=tk.WORD, height=25, width=80, font=('Consolas', 10))
        self.details_text.pack(padx=10, pady=10, fill='both', expand=True)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.load_details_stats()

    def load_overview_stats(self):
        try:
            if self.overview_text:
                self.overview_text.delete(1.0, tk.END)

                self.cursor_master.execute("SELECT COUNT(*) FROM Playlists")
                total_records = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Artist) FROM Playlists WHERE Artist IS NOT NULL AND Artist != ''")
                unique_artists = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Title) FROM Playlists WHERE Title IS NOT NULL AND Title != ''")
                unique_titles = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Label) FROM Playlists WHERE Label IS NOT NULL AND Label != ''")
                unique_labels = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT DJ) FROM Playlists WHERE DJ IS NOT NULL AND DJ != ''")
                unique_djs = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Club) FROM Playlists WHERE Club IS NOT NULL AND Club != ''")
                unique_clubs = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Town) FROM Playlists WHERE Town IS NOT NULL AND Town != ''")
                unique_towns = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT COUNT(DISTINCT Country) FROM Playlists WHERE Country IS NOT NULL AND Country != ''")
                unique_countries = self.cursor_master.fetchone()[0]

                self.cursor_master.execute("SELECT MIN(Date), MAX(Date) FROM Playlists WHERE Date IS NOT NULL AND Date != ''")
                date_range = self.cursor_master.fetchone()

                overview = f"""
DATABASE OVERVIEW
{'='*50}

Total Entities: {total_records:,}

UNIQUE ENTITIES:
• Artists: {unique_artists:,}
• Song Titles: {unique_titles:,}
• Record Labels: {unique_labels:,}
• DJs: {unique_djs:,}
• Clubs/Venues: {unique_clubs:,}
• Towns/Cities: {unique_towns:,}
• Countries: {unique_countries:,}

DATE RANGE:
• Earliest: {date_range[0] if date_range[0] else 'N/A'}
• Latest: {date_range[1] if date_range[1] else 'N/A'}

DATA COMPLETENESS:
"""

                fields = ['Artist', 'Title', 'Label', 'DJ', 'Club', 'Venue', 'Town', 'Country', 'Date']
                for field in fields:
                    self.cursor_master.execute(f"SELECT COUNT(*) FROM Playlists WHERE {field} IS NOT NULL AND {field} != ''")
                    filled = self.cursor_master.fetchone()[0]
                    percentage = (filled / total_records * 100) if total_records > 0 else 0
                    overview += f"• {field}: {filled:,} ({percentage:.1f}%)\n"

                self.overview_text.insert(tk.END, overview)
            else:
                print("Warning: self.overview_text not initialized.")
        except sqlite3.Error as e:
            if self.overview_text:
                self.overview_text.insert(tk.END, f"Error loading statistics: {str(e)}")
            else:
                messagebox.showerror("Statistics Error", f"Error loading statistics and UI not ready: {str(e)}")


    def load_toplists_stats(self):
        try:
            if not self.top_artists_tree or not self.top_labels_tree or not self.top_djs_tree:
                print("Warning: Toplists Treeviews not initialized.")
                return

            for item in self.top_artists_tree.get_children():
                self.top_artists_tree.delete(item)
            for item in self.top_labels_tree.get_children():
                self.top_labels_tree.delete(item)
            for item in self.top_djs_tree.get_children():
                self.top_djs_tree.delete(item)

            self.cursor_master.execute('SELECT Artist, COUNT(*) as count FROM Playlists WHERE Artist IS NOT NULL AND Artist != "" GROUP BY Artist ORDER BY count DESC LIMIT 50')
            for artist, count in self.cursor_master.fetchall():
                self.top_artists_tree.insert('', 'end', values=(artist, count))

            self.cursor_master.execute('SELECT Label, COUNT(*) as count FROM Playlists WHERE Label IS NOT NULL AND Label != "" GROUP BY Label ORDER BY count DESC LIMIT 50')
            for label, count in self.cursor_master.fetchall():
                self.top_labels_tree.insert('', 'end', values=(label, count))

            self.cursor_master.execute('SELECT DJ, COUNT(*) as count FROM Playlists WHERE DJ IS NOT NULL AND DJ != "" GROUP BY DJ ORDER BY count DESC LIMIT 50')
            for dj, count in self.cursor_master.fetchall():
                self.top_djs_tree.insert('', 'end', values=(dj, count))

        except sqlite3.Error as e:
            messagebox.showerror("Statistics Error", str(e))

    def load_details_stats(self):
        try:
            if self.details_text:
                self.details_text.delete(1.0, tk.END)

                details = "DETAILED STATISTICS\n" + "="*50 + "\n\n"

                details += "COUNTRY BREAKDOWN:\n" + "-"*30 + "\n"
                self.cursor_master.execute('SELECT Country, COUNT(*) as count FROM Playlists WHERE Country IS NOT NULL AND Country != "" GROUP BY Country ORDER BY count DESC')
                for country, count in self.cursor_master.fetchall():
                    details += f"{country:<20} {count:>6,}\n"

                details += "\n\nTOP CLUBS/VENUES:\n" + "-"*30 + "\n"
                self.cursor_master.execute('SELECT Club, COUNT(*) as count FROM Playlists WHERE Club IS NOT NULL AND Club != "" GROUP BY Club ORDER BY count DESC LIMIT 30')
                for club, count in self.cursor_master.fetchall():
                    details += f"{club:<30} {count:>6,}\n"

                details += "\n\nTOP TOWNS/CITIES:\n" + "-"*30 + "\n"
                self.cursor_master.execute('SELECT Town, COUNT(*) as count FROM Playlists WHERE Town IS NOT NULL AND Town != "" GROUP BY Town ORDER BY count DESC LIMIT 30')
                for town, count in self.cursor_master.fetchall():
                    details += f"{town:<25} {count:>6,}\n"

                details += "\n\nYEAR BREAKDOWN:\n" + "-"*30 + "\n"
                year_data = {}

                self.cursor_master.execute("SELECT DISTINCT Date FROM Playlists WHERE Date IS NOT NULL AND Date != '' LIMIT 10")
                sample_dates = [row[0] for row in self.cursor_master.fetchall()]

                if sample_dates:
                    details += f"Sample dates: {', '.join(sample_dates[:5])}\n\n"

                try:
                    self.cursor_master.execute('SELECT SUBSTR(Date, -4) as year, COUNT(*) as count FROM Playlists WHERE Date IS NOT NULL AND Date != "" AND LENGTH(Date) >= 4 GROUP BY year ORDER BY year DESC')
                    results = self.cursor_master.fetchall()
                    for year, count in results:
                        if year and year.isdigit() and 1900 <= int(year) <= 2030:
                            year_data[year] = year_data.get(year, 0) + count

                    if not year_data:
                        self.cursor_master.execute('SELECT SUBSTR(Date, 1, 4) as year, COUNT(*) as count FROM Playlists WHERE Date IS NOT NULL AND Date != "" AND LENGTH(Date) >= 4 GROUP BY year ORDER BY year DESC')
                        results = self.cursor_master.fetchall()
                        for year, count in results:
                            if year and year.isdigit() and 1900 <= int(year) <= 2030:
                                year_data[year] = year_data.get(year, 0) + count

                    if not year_data:
                        self.cursor_master.execute("SELECT Date FROM Playlists WHERE Date IS NOT NULL AND Date != ''")
                        all_dates = self.cursor_master.fetchall()

                        import re
                        year_pattern = re.compile(r'\b(19|20)\d{2}\b')

                        for (date_str,) in all_dates:
                            match = year_pattern.search(str(date_str))
                            if match:
                                year = match.group()
                                year_data[year] = year_data.get(year, 0) + 1

                    if year_data:
                        for year in sorted(year_data.keys(), reverse=True):
                            details += f"{year:<10} {year_data[year]:>6,}\n"
                    else:
                        details += "No recognizable year data found in date fields\n"

                except Exception as e:
                    details += f"Error parsing dates: {str(e)}\n"

                try:
                    self.cursor_master.execute("SELECT Date, COUNT(*) FROM Playlists WHERE Date IS NOT NULL AND Date != '' GROUP BY Date ORDER BY COUNT(*) DESC LIMIT 10")
                    common_dates = self.cursor_master.fetchall()
                    if common_dates:
                        details += f"\nMost common date values:\n"
                        for date_val, count in common_dates:
                            details += f"  '{date_val}' appears {count} times\n"
                except:
                    pass

                self.details_text.insert(tk.END, details)
            else:
                print("Warning: self.details_text not initialized.")
        except sqlite3.Error as e:
            if self.details_text:
                self.details_text.insert(tk.END, f"Error loading detailed statistics: {str(e)}")
            else:
                messagebox.showerror("Statistics Error", f"Error loading detailed statistics and UI not ready: {str(e)}")

    def refresh_stats(self):
        self.load_overview_stats()
        self.load_toplists_stats()
        self.load_details_stats()
        messagebox.showinfo("Statistics", "Statistics refreshed successfully!")

    def create_search_controls(self, parent):
        self.search_vars = {
            'artist': tk.StringVar(),
            'title': tk.StringVar(),
            'label': tk.StringVar(),
            'date': tk.StringVar(),
            'dj': tk.StringVar(),
            'club': tk.StringVar(),
            'town': tk.StringVar(),
            'country': tk.StringVar(),
        }

        row = 0

        for field, var_name in [('Artist', 'artist'), ('Title', 'title'), ('Label', 'label'), ('Date', 'date')]:
            ttk.Label(parent, text=field + ":").grid(row=row, column=0, sticky=tk.W, pady=2)
            entry = ttk.Entry(parent, textvariable=self.search_vars[var_name], width=25)
            entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5,0))
            entry.bind('<Return>', lambda e: self.search())
            row += 1

        self.dropdowns = {}
        for field, var_name in [('DJ', 'dj'), ('Club', 'club'), ('Town', 'town'), ('Country', 'country')]:
            ttk.Label(parent, text=field + ":").grid(row=row, column=0, sticky=tk.W, pady=2)
            combo = ttk.Combobox(parent, textvariable=self.search_vars[var_name], width=23, state="readonly")
            combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5,0))
            combo.bind('<<ComboboxSelected>>', lambda e: self.search())
            self.dropdowns[var_name] = combo
            row += 1

        ttk.Button(parent, text="Search", command=self.search).grid(row=row, column=0, pady=10, sticky=tk.W)
        ttk.Button(parent, text="Clear", command=self.clear_search).grid(row=row, column=1, pady=10, sticky=tk.W)
        row += 1

        ttk.Button(parent, text="Add to Playlist", command=self.add_to_playlist).grid(row=row, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        row += 1
        ttk.Button(parent, text="Download Audio (MP3)", command=lambda: self.download_audio('search')).grid(row=row, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        row += 1
        ttk.Button(parent, text="Export CSV", command=self.export_csv).grid(row=row, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        row += 1

        # --- Project Team button ---
        ttk.Button(parent, text="Project Team", command=self.show_credits_window).grid(row=row, column=0, columnspan=2, pady=(15, 5), sticky=(tk.W, tk.E))
        row += 1

    # --- Methods for Download Logic ---
    def download_audio(self, source='search'):
        if source == 'search':
            artist, title = self.get_selected_track()
        else:
            selection = self.playlist_contents_tree.selection()
            if not selection:
                messagebox.showwarning("No Selection", "Please select a track first.")
                return
            values = self.playlist_contents_tree.item(selection[0], 'values')
            artist, title = values[0], values[1]

        if not artist or not title:
            messagebox.showwarning("No Selection", "Please select a track first.")
            return

        download_path = filedialog.askdirectory(title="Select Folder to Save MP3")
        if not download_path:
            return

        threading.Thread(target=self._execute_download, args=(artist, title, download_path), daemon=True).start()

    def _execute_download(self, artist, title, folder):
        search_query = f"ytsearch1:{artist} {title}"
        local_ffmpeg_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{folder}/%(title)s.%(ext)s',
            'ffmpeg_location': local_ffmpeg_dir, 
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([search_query])
            messagebox.showinfo("Success", f"Download Complete:\n{artist} - {title}")
        except Exception as e:
            messagebox.showerror("Download Error", f"An error occurred: {str(e)}\n\nEnsure ffmpeg.exe is in the application folder.")

    def show_credits_window(self):
        credits_window = tk.Toplevel(self.root)
        credits_window.title("Project Supporters")
        credits_window.geometry("450x500") # Made slightly wider for columns
        credits_window.resizable(False, False)
        credits_window.transient(self.root)
        credits_window.grab_set()

        legend_label = ttk.Label(credits_window, text="Thanks to everyone involved in the project", font=('TkDefaultFont', 10, 'italic'))
        legend_label.pack(pady=(10, 5))

        credits_canvas = tk.Canvas(credits_window, bg='black')
        credits_canvas.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        # --- Logic to read static credits from credits.json ---
        static_credits_text = ""
        try:
            with open(resource_path('credits.json'), 'r') as f:
                data = json.load(f)
                for category, names in data.items():
                    static_credits_text += f"--- {category} ---\n\n"
                    static_credits_text += "\n".join(names)
                    static_credits_text += "\n\n\n"
        except FileNotFoundError:
            print("Note: 'credits.json' file not found. Skipping static credits.")
        except json.JSONDecodeError:
            static_credits_text = "Error: Could not read 'credits.json'.\nPlease check its formatting.\n\n\n"

        # --- Get the dynamic DJ list from the database ---
        dj_credits_text = ""
        try:
            self.cursor_master.execute("SELECT DISTINCT DJ FROM Playlists WHERE DJ IS NOT NULL AND DJ != '' ORDER BY DJ")
            djs = [row[0] for row in self.cursor_master.fetchall()]

            if djs:
                dj_credits_text = "--- DJs ---\n\n"
                formatted_lines = []
                for i in range(0, len(djs), 2):
                    left_dj = djs[i]
                    right_dj = djs[i+1] if i + 1 < len(djs) else ""
                    formatted_lines.append(f"{left_dj:<25}{right_dj}")
                dj_credits_text += "\n".join(formatted_lines)
            else:
                dj_credits_text = "--- DJs ---\n\nNo DJs found in the database."
        except sqlite3.Error as e:
            dj_credits_text = f"Error fetching DJs: {e}"

        full_credits_text = static_credits_text + dj_credits_text
        canvas_width = 450
        text_item_id = credits_canvas.create_text(
            canvas_width / 2, 500,
            text=full_credits_text,
            fill='white',
            font=('Consolas', 10),
            anchor='n',
            width=canvas_width - 20
        )
        credits_canvas.after(1, self.scroll_credits, credits_canvas, text_item_id)

    def scroll_credits(self, canvas, text_id):
        try:
            canvas.move(text_id, 0, -1)
            x0, y0, x1, y1 = canvas.bbox(text_id)
            if y1 > 0:
                canvas.after(30, self.scroll_credits, canvas, text_id)
        except tk.TclError:
            pass

    def create_results_table(self, parent):
        self.results_label = ttk.Label(parent, text="All Records")
        self.results_label.grid(row=0, column=0, sticky=tk.W, pady=(0,5))

        table_frame = ttk.Frame(parent)
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ('Artist', 'Title', 'Label', 'DJ', 'Club', 'Venue', 'Town', 'Country', 'Date')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)

        widths = {'Artist': 120, 'Title': 150, 'Label': 120, 'DJ': 100, 'Club': 80, 'Venue': 80, 'Town': 80, 'Country': 80, 'Date': 80}
        for col in columns:
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_column(c))
            self.tree.column(col, width=widths[col], minwidth=50)

        v_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        h_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scroll.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.tree.bind('<Double-1>', self.on_double_click)
        self.tree.bind('<Button-3>', self.show_context_menu)

        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Add to Playlist", command=self.add_to_playlist)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Search YouTube", command=lambda: self.open_link('youtube'))
        self.context_menu.add_command(label="Search Spotify", command=lambda: self.open_link('spotify'))
        self.context_menu.add_command(label="Search Discogs", command=lambda: self.open_link('discogs'))

    def populate_dropdowns(self):
        dropdown_fields = ['DJ', 'Club', 'Town', 'Country']
        for field in dropdown_fields:
            if field.lower() in self.dropdowns:
                combo = self.dropdowns[field.lower()]
                try:
                    query = f"SELECT DISTINCT {field} FROM Playlists WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}"
                    self.cursor_master.execute(query)
                    values = [row[0] for row in self.cursor_master.fetchall()]
                    combo['values'] = [''] + values
                except sqlite3.Error as e:
                    print(f"Error populating dropdown for {field}: {e}")
                    combo['values'] = ['']


    def load_data(self, query=None, params=None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        select_cols = "Artist, Title, Label, DJ, Club, Venue, Town, Country, Date"
        if query is None:
            query = f"SELECT {select_cols} FROM Playlists ORDER BY Date DESC LIMIT 500"
            params = []

        try:
            self.cursor_master.execute(query, params)
            rows = self.cursor_master.fetchall()

            for row in rows:
                display_row = [str(item) if item is not None else '' for item in row]
                self.tree.insert('', 'end', values=display_row)

            count = len(rows)
            self.results_label.config(text=f"Results: {count} records")

        except sqlite3.Error as e:
            messagebox.showerror("Database Error", str(e))

    def search(self):
        conditions = []
        params = []

        for field_name, var_name in self.search_vars.items():
            value = var_name.get().strip()
            if value:
                if field_name in ['dj', 'club', 'town', 'country']:
                    conditions.append(f"{field_name.title()} = ?")
                    params.append(value)
                else:
                    conditions.append(f"{field_name.title()} LIKE ?")
                    params.append(f"%{value}%")

        select_cols = "Artist, Title, Label, DJ, Club, Venue, Town, Country, Date"
        base_query = f"SELECT {select_cols} FROM Playlists"
        if conditions:
            query = base_query + " WHERE " + " AND ".join(conditions) + " ORDER BY Date DESC"
        else:
            query = base_query + " ORDER BY Date DESC LIMIT 500"

        self.load_data(query, params)

    def clear_search(self):
        for var in self.search_vars.values():
            var.set('')
        for combo in self.dropdowns.values():
            combo.set('')
        self.load_data()

    def sort_column(self, col):
        data = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]
        try:
            data.sort(key=lambda x: float(x[0]) if x[0] and x[0].replace('.', '', 1).isdigit() else x[0].lower())
        except ValueError:
            data.sort(key=lambda x: str(x[0]).lower())
        for index, (val, item) in enumerate(data):
            self.tree.move(item, '', index)

    def get_selected_track(self):
        selection = self.tree.selection()
        if not selection: return None, None
        item = selection[0]
        values = self.tree.item(item, 'values')
        return (values[0], values[1]) if len(values) >= 2 else (None, None)

    def open_link(self, service):
        artist, title = self.get_selected_track()
        if not artist or not title:
            messagebox.showwarning("No Selection", "Please select a track first.")
            return
        search_term = f"{artist} {title}"
        urls = {
            'youtube': f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_term)}",
            'spotify': f"https://open.spotify.com/search/{urllib.parse.quote(search_term)}",
            'discogs': f"https://www.discogs.com/search/?q={urllib.parse.quote(search_term)}&type=all"
        }
        if service in urls: webbrowser.open(urls[service])

    def on_double_click(self, event): self.open_link('youtube')

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def export_csv(self):
        items = self.tree.get_children()
        if not items: return
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if file_path:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Artist', 'Title', 'Label', 'DJ', 'Club', 'Venue', 'Town', 'Country', 'Date'])
                for item in items: writer.writerow(self.tree.item(item, 'values'))

    def create_playlist(self):
        name = simpledialog.askstring("New Playlist", "Enter playlist name:")
        if name:
            try:
                self.cursor_playlists.execute("INSERT INTO user_playlists (name) VALUES (?)", (name,))
                self.conn_playlists.commit(); self.load_playlists()
            except sqlite3.IntegrityError: messagebox.showerror("Error", "Playlist name already exists!")

    def rename_playlist(self):
        selection = self.playlist_tree.selection()
        if not selection: return
        item_id = selection[0]; current_name = self.playlist_tree.item(item_id, 'text')
        new_name = simpledialog.askstring("Rename", "New name:", initialvalue=current_name)
        if new_name and new_name != current_name:
            p_id = self.playlist_tree.item(item_id, 'tags')[0]
            self.cursor_playlists.execute("UPDATE user_playlists SET name = ? WHERE id = ?", (new_name, p_id))
            self.conn_playlists.commit(); self.load_playlists()

    def delete_playlist(self):
        selection = self.playlist_tree.selection()
        if not selection: return
        item_id = selection[0]; name = self.playlist_tree.item(item_id, 'text')
        if messagebox.askyesno("Confirm", f"Delete '{name}'?"):
            p_id = self.playlist_tree.item(item_id, 'tags')[0]
            self.cursor_playlists.execute("DELETE FROM user_playlists WHERE id = ?", (p_id,))
            self.conn_playlists.commit(); self.load_playlists()
            self.playlist_contents_tree.delete(*self.playlist_contents_tree.get_children())

    def load_playlists(self):
        for item in self.playlist_tree.get_children(): self.playlist_tree.delete(item)
        self.cursor_playlists.execute("SELECT up.id, up.name, up.created_date, COUNT(pi.id) FROM user_playlists up LEFT JOIN playlist_items pi ON up.id = pi.playlist_id GROUP BY up.id ORDER BY up.created_date DESC")
        for p_id, name, created, count in self.cursor_playlists.fetchall():
            self.playlist_tree.insert('', 'end', text=name, values=(count, created.split()[0]), tags=(p_id,))

    def on_playlist_select(self, event):
        selection = self.playlist_tree.selection()
        if selection:
            item_id = selection[0]; name = self.playlist_tree.item(item_id, 'text'); p_id = self.playlist_tree.item(item_id, 'tags')[0]
            self.playlist_label.config(text=f"Playlist: {name}"); self.load_playlist_contents(p_id)

    def load_playlist_contents(self, playlist_id):
        for item in self.playlist_contents_tree.get_children(): self.playlist_contents_tree.delete(item)
        self.cursor_playlists.execute("SELECT artist, title, label, dj, club, town, country, date FROM playlist_items WHERE playlist_id = ? ORDER BY position", (playlist_id,))
        for row in self.cursor_playlists.fetchall(): self.playlist_contents_tree.insert('', 'end', values=row)

    def add_to_playlist(self):
        selection = self.tree.selection()
        if not selection: return
        self.cursor_playlists.execute("SELECT id, name FROM user_playlists ORDER BY name")
        playlists = self.cursor_playlists.fetchall()
        if not playlists: return
        p_names = [n for _, n in playlists]
        result = simpledialog.askstring("Select", f"Playlists: {', '.join(p_names)}\nEnter name:")
        if not result: return
        selected_id = next((pid for pid, pname in playlists if pname.lower() == result.lower()), None)
        if selected_id:
            vals = self.tree.item(selection[0], 'values')
            self.cursor_playlists.execute("INSERT INTO playlist_items (playlist_id, artist, title, label, dj, club, town, country, date, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_items WHERE playlist_id = ?))", (selected_id, vals[0], vals[1], vals[2], vals[3], vals[4], vals[6], vals[7], vals[8], selected_id))
            self.conn_playlists.commit(); self.load_playlists()

    def remove_from_playlist(self):
        selection = self.playlist_contents_tree.selection()
        if not selection or not self.playlist_tree.selection(): return
        p_id = self.playlist_tree.item(self.playlist_tree.selection()[0], 'tags')[0]
        vals = self.playlist_contents_tree.item(selection[0], 'values')
        self.cursor_playlists.execute("DELETE FROM playlist_items WHERE playlist_id = ? AND artist = ? AND title = ? LIMIT 1", (p_id, vals[0], vals[1]))
        self.conn_playlists.commit(); self.load_playlist_contents(p_id); self.load_playlists()

    def move_track(self, direction):
        selection = self.playlist_contents_tree.selection()
        if not selection or not self.playlist_tree.selection(): return
        p_id = self.playlist_tree.item(self.playlist_tree.selection()[0], 'tags')[0]
        item_iid = selection[0]; all_iids = self.playlist_contents_tree.get_children()
        idx = all_iids.index(item_iid); new_idx = idx + direction
        if 0 <= new_idx < len(all_iids):
            vals = self.playlist_contents_tree.item(item_iid, 'values')
            self.cursor_playlists.execute("SELECT id, position FROM playlist_items WHERE playlist_id = ? AND artist = ? AND title = ?", (p_id, vals[0], vals[1]))
            tid, pos = self.cursor_playlists.fetchone()
            target_vals = self.playlist_contents_tree.item(all_iids[new_idx], 'values')
            self.cursor_playlists.execute("SELECT id, position FROM playlist_items WHERE playlist_id = ? AND artist = ? AND title = ?", (p_id, target_vals[0], target_vals[1]))
            oid, opos = self.cursor_playlists.fetchone()
            self.cursor_playlists.execute("UPDATE playlist_items SET position = ? WHERE id = ?", (opos, tid))
            self.cursor_playlists.execute("UPDATE playlist_items SET position = ? WHERE id = ?", (pos, oid))
            self.conn_playlists.commit(); self.load_playlist_contents(p_id)

    def export_playlist(self):
        selection = self.playlist_tree.selection()
        if not selection: return
        p_id = self.playlist_tree.item(selection[0], 'tags')[0]; name = self.playlist_tree.item(selection[0], 'text')
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{name}.csv")
        if path:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f); writer.writerow(['Artist', 'Title', 'Label', 'DJ', 'Club', 'Town', 'Country', 'Date'])
                self.cursor_playlists.execute("SELECT artist, title, label, dj, club, town, country, date FROM playlist_items WHERE playlist_id = ? ORDER BY position", (p_id,))
                for row in self.cursor_playlists.fetchall(): writer.writerow(row)

    def show_playlist_context_menu(self, event):
        item = self.playlist_contents_tree.identify_row(event.y)
        if item: self.playlist_contents_tree.selection_set(item); self.playlist_context_menu.post(event.x_root, event.y_root)

    def on_playlist_double_click(self, event): self.open_playlist_link('youtube')

    def on_toplist_double_click(self, event, field_type):
        tree = {'Artist': self.top_artists_tree, 'Label': self.top_labels_tree, 'DJ': self.top_djs_tree}.get(field_type)
        if tree and tree.selection():
            val = tree.item(tree.selection()[0], 'values')[0]
            self.notebook.select(self.search_frame); self.clear_search()
            if field_type.lower() in self.search_vars: self.search_vars[field_type.lower()].set(val)
            self.search()

    def open_playlist_link(self, service):
        selection = self.playlist_contents_tree.selection()
        if selection:
            vals = self.playlist_contents_tree.item(selection[0], 'values')
            artist, title = vals[0], vals[1]; q = urllib.parse.quote(f"{artist} {title}")
            urls = {'youtube': f"https://www.youtube.com/results?search_query={q}", 'spotify': f"https://open.spotify.com/search/{q}", 'discogs': f"https://www.discogs.com/search/?q={q}&type=all"}
            webbrowser.open(urls[service])

if __name__ == "__main__":
    root = tk.Tk(); root.withdraw()
    splash = tk.Toplevel(root); splash.overrideredirect(True)
    try:
        img = Image.open(resource_path("Rare Soul Playlists.png")); splash_photo = ImageTk.PhotoImage(img)
        splash.geometry(f"{img.width}x{img.height}+{(root.winfo_screenwidth()//2)-(img.width//2)}+{(root.winfo_screenheight()//2)-(img.height//2)}")
        tk.Label(splash, image=splash_photo, borderwidth=0).pack()
    except:
        splash.geometry("300x100"); tk.Label(splash, text="Loading Application...", font=("Helvetica", 16)).pack(pady=30)
    splash.update(); app = MinimalPlaylistApp(root); splash.destroy(); root.deiconify()
    def on_closing():
        if app.conn_master: app.conn_master.close()
        if app.conn_playlists: app.conn_playlists.close()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing); root.mainloop()