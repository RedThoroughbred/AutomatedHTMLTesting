import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os
import sys
import json
import pandas as pd
import threading
import subprocess
import time
from datetime import datetime

class AutomatedHTMLTester:
    def __init__(self, root):
        self.root = root
        self.root.title("Automated HTML Tester")
        self.root.geometry("900x700")
        
        # Variables
        self.url_var = tk.StringVar()
        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.test_file_var = tk.StringVar(value="test_cases.csv")
        self.headless_var = tk.BooleanVar(value=False)
        self.save_screenshots_var = tk.BooleanVar(value=True)
        self.wait_time_var = tk.DoubleVar(value=2.0)
        self.platform_type_var = tk.StringVar(value="web")
        
        # Create main notebook (tabs)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create tabs
        self.setup_tab = ttk.Frame(self.notebook)
        self.results_tab = ttk.Frame(self.notebook)
        self.config_tab = ttk.Frame(self.notebook)
        
        self.notebook.add(self.setup_tab, text="Test Setup")
        self.notebook.add(self.results_tab, text="Test Results")
        self.notebook.add(self.config_tab, text="Configuration")
        
        # Build UI for each tab
        self._build_setup_tab()
        self._build_results_tab()
        self._build_config_tab()
        
        # Initialize working directory
        self.working_dir = os.getcwd()
        
        # Track test process
        self.test_process = None
        self.update_timer = None
        
    def _build_setup_tab(self):
        # Create a frame for input fields
        input_frame = ttk.LabelFrame(self.setup_tab, text="Test Parameters")
        input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Website URL
        ttk.Label(input_frame, text="Website URL:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.url_var, width=50).grid(row=0, column=1, columnspan=2, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # Login credentials (optional)
        ttk.Label(input_frame, text="Username (optional):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.username_var, width=30).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Password (optional):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.password_var, width=30, show="*").grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Test file selection
        ttk.Label(input_frame, text="Test Cases File:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(input_frame, textvariable=self.test_file_var, width=40).grid(row=3, column=1, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Button(input_frame, text="Browse...", command=self._browse_test_file).grid(row=3, column=2, padx=5, pady=5)
        
        # Platform type
        ttk.Label(input_frame, text="Platform Type:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        platform_dropdown = ttk.Combobox(input_frame, textvariable=self.platform_type_var, values=["web", "pro", "app"])
        platform_dropdown.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        platform_dropdown.current(0)
        
        # Test options frame
        options_frame = ttk.LabelFrame(self.setup_tab, text="Test Options")
        options_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Headless mode
        ttk.Checkbutton(options_frame, text="Run in Headless Mode", variable=self.headless_var).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        # Save screenshots
        ttk.Checkbutton(options_frame, text="Save All Screenshots", variable=self.save_screenshots_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Wait time
        ttk.Label(options_frame, text="Wait Time (seconds):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Spinbox(options_frame, from_=0.5, to=10.0, increment=0.5, textvariable=self.wait_time_var, width=5).grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Button frame
        button_frame = ttk.Frame(self.setup_tab)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Run test button
        ttk.Button(button_frame, text="Run Tests", command=self._run_tests, style="Accent.TButton").pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Save config button
        ttk.Button(button_frame, text="Save Configuration", command=self._save_config).pack(side=tk.RIGHT, padx=5, pady=5)
        
    def _build_results_tab(self):
        # Create frames for results and log
        results_frame = ttk.LabelFrame(self.results_tab, text="Test Results")
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Results display (read-only text widget)
        self.results_text = scrolledtext.ScrolledText(results_frame, width=80, height=20, wrap=tk.WORD)
        self.results_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.results_text.config(state=tk.DISABLED)
        
        # Buttons frame
        button_frame = ttk.Frame(self.results_tab)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Clear results button
        ttk.Button(button_frame, text="Clear Results", command=self._clear_results).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Open results folder button
        ttk.Button(button_frame, text="Open Results Folder", command=self._open_results_folder).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Export results button
        ttk.Button(button_frame, text="Export Results", command=self._export_results).pack(side=tk.RIGHT, padx=5, pady=5)
        
    def _build_config_tab(self):
        # Create frames for configuration
        config_frame = ttk.LabelFrame(self.config_tab, text="Configuration Editor")
        config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Platform selection for config
        ttk.Label(config_frame, text="Select Configuration:").pack(anchor=tk.W, padx=5, pady=5)
        
        config_platform_frame = ttk.Frame(config_frame)
        config_platform_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.config_platform_var = tk.StringVar(value="web")
        
        ttk.Radiobutton(config_platform_frame, text="Web", variable=self.config_platform_var, value="web", 
                      command=self._load_selected_config).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(config_platform_frame, text="Pro", variable=self.config_platform_var, value="pro", 
                      command=self._load_selected_config).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(config_platform_frame, text="App", variable=self.config_platform_var, value="app", 
                      command=self._load_selected_config).pack(side=tk.LEFT, padx=5)
        
        # Config editor
        ttk.Label(config_frame, text="Edit Configuration JSON:").pack(anchor=tk.W, padx=5, pady=5)
        
        self.config_text = scrolledtext.ScrolledText(config_frame, width=80, height=20, wrap=tk.WORD)
        self.config_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Buttons for config actions
        config_button_frame = ttk.Frame(config_frame)
        config_button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(config_button_frame, text="Save Changes", command=self._save_config_changes).pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(config_button_frame, text="Reload", command=self._load_selected_config).pack(side=tk.RIGHT, padx=5, pady=5)
        
        # Load the initial config
        self._load_selected_config()

    def _browse_test_file(self):
        filename = filedialog.askopenfilename(
            initialdir=self.working_dir,
            title="Select Test Cases File",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*"))
        )
        if filename:
            self.test_file_var.set(filename)

    def _save_config(self):
        # Get the current values
        platform_type = self.platform_type_var.get()
        url = self.url_var.get()
        username = self.username_var.get()
        password = self.password_var.get()
        
        if not url:
            self._show_error("URL is required")
            return
        
        # Determine the config file to update
        config_file = f"config4{platform_type}.json"
        
        try:
            # Load existing config
            with open(config_file, 'r') as f:
                config = json.load(f)
                
            # Update the URL in the first platform
            if config["platforms"] and len(config["platforms"]) > 0:
                config["platforms"][0]["url"] = url
                
                # If credentials are provided, update them too
                if username and password:
                    config["platforms"][0]["requires_login"] = True
                    config["platforms"][0]["username"] = username
                    config["platforms"][0]["password"] = password
                    
                    # Ensure login_selectors exists for pro platform
                    if platform_type == "pro" and "login_selectors" not in config["platforms"][0]:
                        config["platforms"][0]["login_selectors"] = {
                            "username_field": "#username",  # Default selectors
                            "password_field": "#password",
                            "login_button": "#login_button"
                        }
                
            # Save updated config
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
                
            self._append_to_results(f"Configuration saved to {config_file}")
            
        except Exception as e:
            self._show_error(f"Error saving configuration: {str(e)}")

    def _run_tests(self):
        # Get selected options
        platform_type = self.platform_type_var.get()
        test_file = self.test_file_var.get()
        headless = self.headless_var.get()
        save_screenshots = self.save_screenshots_var.get()
        wait_time = self.wait_time_var.get()
        
        # Validate inputs
        if not test_file:
            self._show_error("Please select a test cases file")
            return
            
        # Determine which script to run
        script_file = f"app4{platform_type}.py"
        
        # Build command
        cmd = [sys.executable, script_file, "--test-set", test_file]
        
        # Add options
        if headless:
            cmd.append("--headless")
        if save_screenshots:
            cmd.append("--save-all-screenshots")
        if wait_time != 2.0:
            cmd.extend(["--wait-time", str(wait_time)])
            
        # Clear results before starting
        self._clear_results()
        self._append_to_results(f"Starting test with command: {' '.join(cmd)}\n")
        
        # Switch to results tab
        self.notebook.select(1)  # Select the results tab
        
        # Run the test in a separate thread to keep UI responsive
        threading.Thread(target=self._run_test_process, args=(cmd,), daemon=True).start()

    def _run_test_process(self, cmd):
        try:
            # Start the process and capture output
            self.test_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Schedule periodic updates
            self._update_results_from_process()
            
        except Exception as e:
            self._append_to_results(f"Error running test: {str(e)}")

    def _update_results_from_process(self):
        if self.test_process is None:
            return
            
        # Check if the process is still running
        if self.test_process.poll() is not None:
            # Process has ended, read any remaining output
            output, _ = self.test_process.communicate()
            if output:
                self._append_to_results(output)
                
            # Get return code
            return_code = self.test_process.returncode
            self._append_to_results(f"\nTest process completed with return code: {return_code}")
            
            # Reset process
            self.test_process = None
            return
        
        # Read output without blocking
        while True:
            output_line = self.test_process.stdout.readline()
            if not output_line:
                break
            self._append_to_results(output_line.strip())
            
        # Schedule next update
        self.update_timer = self.root.after(100, self._update_results_from_process)

    def _clear_results(self):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.config(state=tk.DISABLED)

    def _append_to_results(self, text):
        self.results_text.config(state=tk.NORMAL)
        self.results_text.insert(tk.END, text + "\n")
        self.results_text.see(tk.END)  # Auto-scroll to the bottom
        self.results_text.config(state=tk.DISABLED)

    def _open_results_folder(self):
        # Open the screenshots folder using the default file explorer
        screenshots_path = os.path.join(self.working_dir, "screenshots")
        if os.path.exists(screenshots_path):
            if sys.platform == 'win32':
                os.startfile(screenshots_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.call(['open', screenshots_path])
            else:  # Linux
                subprocess.call(['xdg-open', screenshots_path])
        else:
            self._show_error("Screenshots folder not found")

    def _export_results(self):
        # Find the latest results CSV file
        csv_files = [f for f in os.listdir(self.working_dir) if f.startswith("results_") and f.endswith(".csv")]
        if not csv_files:
            self._show_error("No results files found")
            return
            
        # Sort by modification time (newest first)
        csv_files.sort(key=lambda x: os.path.getmtime(os.path.join(self.working_dir, x)), reverse=True)
        latest_file = csv_files[0]
        
        # Ask where to save the export
        export_path = filedialog.asksaveasfilename(
            initialdir=self.working_dir,
            title="Save Results As",
            initialfile=latest_file,
            defaultextension=".csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*"))
        )
        
        if export_path:
            # Copy the file
            try:
                import shutil
                shutil.copy2(os.path.join(self.working_dir, latest_file), export_path)
                self._append_to_results(f"Results exported to {export_path}")
            except Exception as e:
                self._show_error(f"Error exporting results: {str(e)}")

    def _load_selected_config(self):
        # Get the selected platform
        platform_type = self.config_platform_var.get()
        config_file = f"config4{platform_type}.json"
        
        try:
            # Load the config file
            with open(config_file, 'r') as f:
                config_content = f.read()
                
            # Update the text widget
            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(tk.END, config_content)
            
        except Exception as e:
            self.config_text.delete(1.0, tk.END)
            self.config_text.insert(tk.END, f"Error loading {config_file}: {str(e)}")

    def _save_config_changes(self):
        # Get the selected platform
        platform_type = self.config_platform_var.get()
        config_file = f"config4{platform_type}.json"
        
        try:
            # Get the content from the text widget
            config_content = self.config_text.get(1.0, tk.END)
            
            # Validate JSON
            json.loads(config_content)  # Will raise an exception if invalid
            
            # Save to file
            with open(config_file, 'w') as f:
                f.write(config_content)
                
            # Show success message
            tk.messagebox.showinfo("Success", f"Configuration saved to {config_file}")
            
        except json.JSONDecodeError as e:
            # Show error for invalid JSON
            tk.messagebox.showerror("JSON Error", f"Invalid JSON format: {str(e)}")
        except Exception as e:
            # Show error for other exceptions
            tk.messagebox.showerror("Error", f"Error saving configuration: {str(e)}")

    def _show_error(self, message):
        tk.messagebox.showerror("Error", message)

def main():
    root = tk.Tk()
    
    # Set up visual styles
    style = ttk.Style()
    style.configure("Accent.TButton", font=("Arial", 11, "bold"))
    
    app = AutomatedHTMLTester(root)
    root.mainloop()

if __name__ == "__main__":
    main()