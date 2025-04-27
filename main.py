import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel
import os
import configparser
import json
from ebooklib import epub
import ebooklib
from tkhtmlview import HTMLScrolledText  # For rendering HTML
from PIL import Image, ImageTk
import webbrowser
from dotenv import load_dotenv  # Load .env variables
import tweepy
import traceback  # For detailed error logging
from instagrapi import Client as InstagramClient  # For Instagram posting
from instagrapi.exceptions import LoginRequired, ClientError
from datetime import datetime  # For timestamp in tweets.txt
import subprocess  # For running php build.php
import re  # For natural sorting

# Load environment variables from .env file
load_dotenv()

CONFIG_FILE = os.path.expanduser("~/.book_builder_config.json")

def load_last_path():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_path', ''), data.get('sort_reverse', True)  # Default to reversed
    return '', True

def save_last_path(path, sort_reverse):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'last_path': path, 'sort_reverse': sort_reverse}, f)

def validate_book_dir(path):
    bookshelf_exists = os.path.isdir(os.path.join(path, 'bookshelf'))
    ini_exists = os.path.isfile(os.path.join(path, 'bookshelf/books.ini'))
    return bookshelf_exists and ini_exists

def parse_books_ini(path):
    config = configparser.ConfigParser()
    config.read(os.path.join(path, 'bookshelf/books.ini'))
    return {section: config[section] for section in config.sections()}

def natural_sort_key(s):
    """Key function for natural sorting (e.g., chapter1.md, chapter2.md, chapter10.md)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

class BookBuilderUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Book Builder UI")

        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        width = int(screen_width * 0.9)
        height = int(screen_height * 0.9)
        root.geometry(f"{width}x{height}")

        self.path_var = tk.StringVar()
        self.books = []
        self.sort_reverse = True  # Default to reversed (newest first)
        self.chapter_vars = {}  # Store StringVar instances per book

        self.build_path_selector()
        self.build_book_list()

        last_path, sort_reverse = load_last_path()
        if last_path:
            self.path_var.set(last_path)
            self.sort_reverse = sort_reverse
            self.check_path()

    def build_path_selector(self):
        frame = tk.Frame(self.root)
        frame.pack(pady=10, padx=10, fill='x')

        tk.Label(frame, text="Path to Book System:").pack(side='left')
        entry = tk.Entry(frame, textvariable=self.path_var, width=50)
        entry.pack(side='left', padx=5)

        tk.Button(frame, text="Browse", command=self.browse_path).pack(side='left')
        tk.Button(frame, text="Check", command=self.check_path).pack(side='left', padx=5)

        # Add sort order dropdown
        tk.Label(frame, text="Sort Order:").pack(side='left', padx=5)
        sort_options = ["Newest First", "Oldest First"]
        self.sort_var = tk.StringVar(frame)
        self.sort_var.set("Newest First" if self.sort_reverse else "Oldest First")
        def on_sort_change(*args):
            self.sort_reverse = (self.sort_var.get() == "Newest First")
            save_last_path(self.path_var.get(), self.sort_reverse)
            if self.path_var.get():
                self.refresh_book_list(self.path_var.get())
        self.sort_var.trace('w', on_sort_change)
        sort_dropdown = tk.OptionMenu(frame, self.sort_var, *sort_options)
        sort_dropdown.pack(side='left', padx=5)

    def build_book_list(self):
        self.book_frame = tk.Frame(self.root)
        self.book_frame.pack(padx=10, pady=10, fill='both', expand=True)

        self.canvas = tk.Canvas(self.book_frame)
        self.scrollbar = tk.Scrollbar(self.book_frame, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    def browse_path(self):
        selected_path = filedialog.askdirectory()
        if selected_path:
            self.path_var.set(selected_path)

    def check_path(self):
        path = self.path_var.get()
        if not os.path.isdir(path):
            messagebox.showerror("Invalid Path", "Selected path is not a directory.")
            return

        if validate_book_dir(path):
            save_last_path(path, self.sort_reverse)
            self.refresh_book_list(path)
        else:
            messagebox.showerror("Validation Error", "Directory must contain 'bookshelf/' and 'books.ini'.")
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()

    def refresh_book_list(self, path):
        """Refresh the book list with the current sort order."""
        print("[DEBUG] Refreshing book list")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.chapter_vars.clear()  # Clear old StringVar instances

        books_config = parse_books_ini(path)
        book_list = reversed(books_config) if self.sort_reverse else books_config
        for book in book_list:
            row = tk.Frame(self.scrollable_frame)
            row.pack(fill='x', pady=2)

            tk.Label(row, text=book, width=50, anchor='w').pack(side='left', padx=5)
            
            book_title = books_config[book].get('book[title]', 'unknown')
            tk.Label(row, text=book_title, width=50, anchor='w').pack(side='left', padx=5)

            book_category = books_config[book].get('book[category]', 'unknown')
            tk.Label(row, text=book_category, width=20, anchor='w').pack(side='left', padx=5)

            book_status = books_config[book].get('book[status]', 'unknown')
            tk.Label(row, text=f"{book_status}", width=15, anchor='w').pack(side='left', padx=2)

            build_button = tk.Button(row, text="Build", command=lambda b=book: self.run_command('build', b))
            build_button.pack(side='left', padx=2)
            if book_status.lower() == 'published':
                build_button.config(state='disabled')

            tk.Button(row, text="Clean", command=lambda b=book: self.run_command('clean', b)).pack(side='left', padx=2)

            epub_path = os.path.join(path, 'bookshelf', book, f"{book}.epub")
            preview_button = tk.Button(
                row,
                text="Preview",
                command=lambda b=book: self.preview_book(path, b)
            )
            preview_button.pack(side='left', padx=2)
            if not os.path.isfile(epub_path):
                preview_button.config(state='disabled')

            cover_path = os.path.join(path, 'bookshelf', book, 'media', 'cover-image-template.jpg')
            amazon_us = books_config[book].get('amazon[us]')
            amazon_uk = books_config[book].get('amazon[uk]')
            tweet_button = tk.Button(
                row,
                text="Tweet",
                command=lambda b=book, us=amazon_us, uk=amazon_uk: self.post_to_twitter(path, b, us, uk)
            )
            tweet_button.pack(side='left', padx=2)
            insta_button = tk.Button(
                row,
                text="Insta",
                command=lambda b=book, us=amazon_us, uk=amazon_uk: self.post_to_instagram(path, b, us, uk)
            )
            insta_button.pack(side='left', padx=2)
            if not os.path.exists(cover_path):
                tweet_button.config(state='disabled')
                insta_button.config(state='disabled')

            # Add chapter dropdown only if book directory exists
            book_dir = os.path.join(path, 'bookshelf', book)
            if not os.path.isdir(book_dir):
                print(f"[DEBUG] Skipping chapter dropdown for {book}: No book directory")
                tk.Label(row, text="No book directory", width=20, anchor='w').pack(side='left', padx=2)
                continue

            chapter_files = self.list_chapter_files(path, book)
            print(f"[DEBUG] Chapter files for {book}: {chapter_files}")
            selected_chapter = tk.StringVar(self.root)
            self.chapter_vars[book] = selected_chapter  # Store StringVar
            selected_chapter.set(chapter_files[0])  # Default to first item
            def on_chapter_select(*args, b=book, files=chapter_files):
                selected_value = selected_chapter.get()
                print(f"[DEBUG] Chapter selected: {selected_value} for book: {b}")
                if selected_value not in ["No chapters directory", "No chapter files"]:
                    print(f"[DEBUG] Opening modal for {selected_value}")
                    self.edit_chapter_file(path, b, selected_value)
                else:
                    print(f"[DEBUG] Invalid selection: {selected_value}, no modal opened")
            selected_chapter.trace_add('write', on_chapter_select)
            chapter_dropdown = tk.OptionMenu(row, selected_chapter, *chapter_files)
            chapter_dropdown.pack(side='left', padx=2)
            if chapter_files[0] in ["No chapters directory", "No chapter files"]:
                chapter_dropdown.config(state='disabled')

    def list_chapter_files(self, base_path, book):
        """Return a naturally sorted list of files in the book's chapters directory."""
        chapters_dir = os.path.join(base_path, 'bookshelf', book, 'chapters')
        if not os.path.isdir(chapters_dir):
            return ["No chapters directory"]
        files = [f for f in os.listdir(chapters_dir) if os.path.isfile(os.path.join(chapters_dir, f))]
        if not files:
            return ["No chapter files"]
        return sorted(files, key=natural_sort_key)

    def edit_chapter_file(self, base_path, book, filename):
        """Open a modal to edit the selected chapter file."""
        print(f"[DEBUG] Entering edit_chapter_file: {filename} for book: {book}")
        if filename in ["No chapters directory", "No chapter files"]:
            print(f"[DEBUG] Invalid filename, returning")
            return  # Silently return, no modal for invalid options

        chapters_dir = os.path.join(base_path, 'bookshelf', book, 'chapters')
        file_path = os.path.join(chapters_dir, filename)

        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"[DEBUG] Successfully read {filename}")
        except Exception as e:
            print(f"[DEBUG] Failed to read {filename}: {e}")
            messagebox.showerror("Error", f"Failed to read {filename}: {e}")
            return

        # Create modal window
        modal = Toplevel(self.root)
        modal.title(f"Edit Chapter: {filename}")
        #modal.geometry("800x600")  # Increased size
        modal.geometry("1000x1200")  # Increased size
        modal.transient(self.root)  # Make modal stay on top
        modal.grab_set()  # Capture input to modal
        print(f"[DEBUG] Modal opened for {filename}")

        # Create frame for textarea and scrollbar
        text_frame = tk.Frame(modal)
        text_frame.pack(padx=10, pady=10, fill='both', expand=True)

        # Add textarea with scrollbar
        textarea = tk.Text(text_frame, wrap='word', height=30, width=80)  # Increased size
        scrollbar = tk.Scrollbar(text_frame, orient='vertical', command=textarea.yview)
        textarea.configure(yscrollcommand=scrollbar.set)
        textarea.insert('1.0', content)
        textarea.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # Save and Cancel buttons
        def save_file():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(textarea.get('1.0', 'end-1c'))
                messagebox.showinfo("Success", f"Saved changes to {filename}")
                modal.destroy()
                print(f"[DEBUG] Saved {filename} and closed modal")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save {filename}: {e}")
                print(f"[DEBUG] Failed to save {filename}: {e}")

        tk.Button(modal, text="Save", command=save_file).pack(side='left', padx=5, pady=5)
        tk.Button(modal, text="Cancel", command=modal.destroy).pack(side='left', padx=5, pady=5)

    def run_command(self, command, book):
        try:
            base_path = self.path_var.get()
            work_dir = os.path.join(base_path, 'bookshelf')
            php_script = os.path.join(work_dir, 'build.php')
            
            if not os.path.isdir(work_dir):
                messagebox.showerror("Error", f"Directory not found: {work_dir}")
                return
            if not os.path.isfile(php_script):
                messagebox.showerror("Error", f"build.php not found at {php_script}")
                return

            if command == 'build':
                cmd = ['php', php_script, book]
            elif command == 'clean':
                cmd = ['php', php_script, '--clean', book]
            else:
                messagebox.showerror("Error", f"Unknown command: {command}")
                return

            print(f"[DEBUG] Running command: {' '.join(cmd)} in {work_dir}")
            result = subprocess.run(
                cmd,
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode == 0:
                messagebox.showinfo("Success", f"{command.capitalize()} completed for {book}\nOutput:\n{result.stdout}")
            else:
                messagebox.showerror(
                    "Error",
                    f"{command.capitalize()} failed for {book}\nError:\n{result.stderr}\nOutput:\n{result.stdout}"
                )
            print(f"[DEBUG] {command} result: returncode={result.returncode}, stdout={result.stdout}, stderr={result.stderr}")

        except FileNotFoundError:
            messagebox.showerror("Error", "PHP executable not found. Ensure PHP is installed and in PATH.")
            print("[ERROR] PHP executable not found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run {command} for {book}: {e}")
            print(f"[ERROR] Failed to run {command}: {e}")

    def preview_book(self, base_path, book):
        epub_path = os.path.join(base_path, 'bookshelf', book, f"{book}.epub")
        if not os.path.isfile(epub_path):
            messagebox.showwarning("File Not Found", f"EPUB not found for {book} at {epub_path}")
            return

        try:
            book_obj = epub.read_epub(epub_path)
            preview_window = Toplevel(self.root)
            preview_window.title(f"Preview: {book}")
            preview_window.geometry("800x600")

            html_view = HTMLScrolledText(preview_window, html="", wrap='word')
            html_view.pack(expand=True, fill='both')

            title = book_obj.get_metadata('DC', 'title')
            author = book_obj.get_metadata('DC', 'creator')
            html_content = f"<h2>{title[0][0] if title else 'Unknown'}</h2>"
            html_content += f"<h4>by {author[0][0] if author else 'Unknown'}</h4><hr>"

            for item in book_obj.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                html_content += item.get_content().decode('utf-8') + "<br><br>"

            html_view.set_html(html_content)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read EPUB: {e}")

    def post_to_twitter(self, base_path, book, amazon_us=None, amazon_uk=None):
        try:
            epub_path = os.path.join(base_path, 'bookshelf', book, f"{book}.epub")
            cover_path = os.path.join(base_path, 'bookshelf', book, 'media', 'cover-image-template.jpg')

            if not os.path.isfile(epub_path):
                messagebox.showerror("Missing File", "EPUB file not found.")
                return

            books_config = parse_books_ini(base_path)
            book_title = books_config[book].get('book[title]', 'unknown')
            book_subtitle = books_config[book].get('book[subtitle]', 'unknown')
            amazon_us = books_config[book].get('amazon[us]')
            amazon_uk = books_config[book].get('amazon[uk]')

            if not (amazon_us or amazon_uk):
                messagebox.showwarning(
                    "Missing Amazon Links",
                    "Cannot post tweet: At least one of amazon[us] or amazon[uk] is required in books.ini."
                )
                return

            if book_title == 'unknown' or book_subtitle == 'unknown':
                messagebox.showwarning(
                    "Missing Metadata",
                    "Cannot post tweet: book[title] or book[subtitle] missing in books.ini."
                )
                return

            book_obj = epub.read_epub(epub_path)
            author = book_obj.get_metadata('DC', 'creator')

            base_text = (
                f"Discover a new book: {book_title}. {book_subtitle}. "
                f"Written by {author[0][0] if author else 'an unknown author'}. "
                f"This engaging read is now available for you to explore!"
            )

            cta_text = "Here's the link to buy:"
            if amazon_us:
                cta_text += f"\n🇺🇸 US: {amazon_us}"
            if amazon_uk:
                cta_text += f"\n🇬🇧 UK: {amazon_uk}"

            if len(base_text) > 280:
                base_text = base_text[:277] + "..."

            if len(cta_text) > 280:
                cta_text = cta_text[:277] + "..."

            print("[DEBUG] Main Tweet Text:", base_text.encode('utf-8', 'replace').decode())
            print("[DEBUG] Reply Text:", cta_text.encode('utf-8', 'replace').decode())

            cover_status = "with cover image" if os.path.isfile(cover_path) else "without cover image"
            preview_message = f"Post this tweet {cover_status}?\n\nMain Tweet:\n{base_text}"
            preview_message += f"\n\nReply with Links (posted after 60s):\n{cta_text}"
            if not messagebox.askyesno("Confirm Tweet", preview_message):
                print("[DEBUG] Tweet posting cancelled by user")
                messagebox.showinfo("Cancelled", "Tweet posting cancelled.")
                return

            consumer_key = os.getenv("TWITTER_API_KEY")
            consumer_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

            if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
                raise ValueError("Missing OAuth 1.0a credentials")

            client = tweepy.Client(
                consumer_key=consumer_key,
                consumer_secret=consumer_secret,
                access_token=access_token,
                access_token_secret=access_token_secret
            )

            auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
            api = tweepy.API(auth)

            media_id = None
            if os.path.isfile(cover_path):
                try:
                    media = api.media_upload(cover_path)
                    media_id = media.media_id
                    print("[DEBUG] Media ID:", media_id)
                except Exception as media_error:
                    print("[WARNING] Failed to upload media:", media_error)

            try:
                user = client.get_me()
                print("[DEBUG] Authenticated as:", user.data.username)
            except Exception as auth_error:
                raise Exception(f"Authentication failed: {auth_error}")

            main_tweet_response = client.create_tweet(text=base_text, media_ids=[media_id] if media_id else None)
            print("[DEBUG] Main Tweet response:", main_tweet_response)
            main_tweet_id = main_tweet_response.data['id']

            tweets_file = os.path.join(base_path, 'bookshelf', book, 'tweets.txt')
            try:
                with open(tweets_file, 'a', encoding='utf-8') as f:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    f.write(f"--- Posted at {timestamp} ---\n")
                    f.write(f"Main Tweet (ID: {main_tweet_id}):\n{main_tweet_response.data['text']}\n")
                    f.write("\n")
                print(f"[DEBUG] Saved main tweet to {tweets_file}")
            except Exception as file_error:
                print(f"[WARNING] Failed to write to {tweets_file}: {file_error}")

            def post_reply():
                try:
                    reply_response = client.create_tweet(
                        text=cta_text,
                        in_reply_to_tweet_id=main_tweet_id
                    )
                    print("[DEBUG] Reply Tweet response:", reply_response)

                    try:
                        with open(tweets_file, 'a', encoding='utf-8') as f:
                            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            f.write(f"--- Reply Posted at {timestamp} ---\n")
                            f.write(f"Reply (ID: {reply_response.data['id']}):\n{reply_response.data['text']}\n")
                            f.write("\n")
                        print(f"[DEBUG] Saved reply to {tweets_file}")
                    except Exception as file_error:
                        print(f"[WARNING] Failed to write reply to {tweets_file}: {file_error}")

                    messagebox.showinfo(
                        "Tweeted!",
                        "Main tweet and reply of Amazon links successfully posted to Twitter!"
                    )
                except Exception as reply_error:
                    print("[WARNING] Failed to post reply:", reply_error)
                    messagebox.showwarning(
                        "Partial Success",
                        f"Main tweet posted, but failed to post reply of Amazon links: {reply_error}"
                    )

            self.root.after(60000, post_reply)
            messagebox.showinfo(
                "Tweeted!",
                "Main tweet posted! Reply of Amazon links will be posted in 60 seconds."
            )

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Twitter Error", f"Failed to tweet: {e}")

    def post_to_instagram(self, base_path, book, amazon_us=None, amazon_uk=None):
        try:
            epub_path = os.path.join(base_path, 'bookshelf', book, f"{book}.epub")
            cover_path = os.path.join(base_path, 'bookshelf', book, 'media', 'cover-image-template.jpg')

            if not os.path.isfile(epub_path):
                messagebox.showerror("Missing File", "EPUB file not found.")
                return
            if not os.path.isfile(cover_path):
                messagebox.showerror("Missing File", "Cover image not found.")
                return

            book_obj = epub.read_epub(epub_path)
            title = book_obj.get_metadata('DC', 'title')
            author = book_obj.get_metadata('DC', 'creator')

            base_text = (
                f"📚 New Book: {title[0][0] if title else book}\n"
                f"✍️ Author: {author[0][0] if author else 'Unknown'}\n"
                f"Discover this gem today! #Bookstagram #IndieAuthor #BookLovers "
                f"#NewRelease #ReadersOfInstagram #BookCommunity #AmazonFinds"
            )
            cta_text = ""
            if amazon_us or amazon_uk:
                cta_text = "\n📖 Get it now:"
                if amazon_us:
                    cta_text += f"\n🇺🇸 US: {amazon_us}"
                if amazon_uk:
                    cta_text += f"\n🇬🇧 UK: {amazon_uk}"
            else:
                print("[DEBUG] No Amazon links provided for this book")

            caption = base_text + cta_text

            if len(caption) > 2200:
                max_base_length = 2200 - len(cta_text) - 3
                base_text = base_text[:max_base_length] + "..."
                caption = base_text + cta_text

            print("[DEBUG] Instagram Caption:", caption.encode('utf-8', 'replace').decode())

            preview_message = f"Post this to Instagram with cover image?\n\n{caption}"
            if not messagebox.askyesno("Confirm Instagram Post", preview_message):
                print("[DEBUG] Instagram posting cancelled by user")
                messagebox.showinfo("Cancelled", "Instagram posting cancelled.")
                return

            username = os.getenv("INSTAGRAM_USERNAME")
            password = os.getenv("INSTAGRAM_PASSWORD")

            if not all([username, password]):
                raise ValueError("Missing Instagram credentials")

            client = InstagramClient()
            try:
                client.login(username, password)
                print("[DEBUG] Instagram login successful")
            except LoginRequired:
                raise ValueError("Invalid Instagram credentials")
            except ClientError as auth_error:
                raise Exception(f"Instagram authentication failed: {auth_error}")

            try:
                client.photo_upload(
                    path=cover_path,
                    caption=caption
                )
                print("[DEBUG] Instagram post successful")
                messagebox.showinfo("Posted!", "Successfully posted to Instagram!")
            except Exception as upload_error:
                print("[WARNING] Failed to upload to Instagram:", upload_error)
                raise Exception(f"Failed to post to Instagram: {upload_error}")

            client.logout()

        except Exception as e:
            traceback.print_exc()
            messagebox.showerror("Instagram Error", f"Failed to post to Instagram: {e}")

def main():
    root = tk.Tk()
    app = BookBuilderUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()