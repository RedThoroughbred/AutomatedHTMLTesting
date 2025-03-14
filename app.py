import os
import json
import time
import csv
import pandas as pd
import threading
import subprocess
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'html_test_automation_secret_key'  # Used for flashing messages

# Add now() function to templates
@app.context_processor
def utility_processor():
    return {
        'now': datetime.now,
    }

# Configure upload folder for test case files
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Make directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs('screenshots', exist_ok=True)

# Store test processes and their status
test_processes = {}

# Store scheduled tests
scheduled_tests = []

# Persistent storage for test durations (survives app restarts)
DURATIONS_FILE = 'test_durations.json'

# Load existing durations if available
test_durations = {}
try:
    if os.path.exists(DURATIONS_FILE):
        with open(DURATIONS_FILE, 'r') as f:
            test_durations = json.load(f)
except Exception as e:
    print(f"Error loading test durations: {str(e)}")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    # Get available configuration files
    config_files = [f for f in os.listdir('.') if f.startswith('config4') and f.endswith('.json')]
    configs = []
    
    for cf in config_files:
        try:
            with open(cf, 'r') as f:
                config = json.load(f)
                platform_type = cf.replace('config4', '').replace('.json', '')
                platform_name = config['platforms'][0]['name'] if config.get('platforms') else platform_type
                configs.append({
                    'file': cf,
                    'type': platform_type,
                    'name': platform_name
                })
        except:
            # Skip invalid config files
            continue
    
    # Get available test case files with additional info
    test_files = []
    
    # Check main directory
    for f in os.listdir('.'):
        if f.endswith('.csv') and os.path.isfile(f) and not f.startswith('results_'):
            # Get basic file info
            stats = os.stat(f)
            modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to count test cases
            case_count = 0
            try:
                with open(f, 'r') as file:
                    # Count non-empty lines after header
                    lines = [line for line in file.readlines() if line.strip()]
                    case_count = len(lines) - 1 if len(lines) > 0 else 0
            except:
                pass
                
            test_files.append({
                'path': f,
                'name': f,
                'modified': modified,
                'case_count': case_count
            })
    
    # Check uploads directory
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        if f.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f)
            
            # Get basic file info
            stats = os.stat(filepath)
            modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to count test cases
            case_count = 0
            try:
                with open(filepath, 'r') as file:
                    # Count non-empty lines after header
                    lines = [line for line in file.readlines() if line.strip()]
                    case_count = len(lines) - 1 if len(lines) > 0 else 0
            except:
                pass
                
            test_files.append({
                'path': filepath,
                'name': f + ' (uploaded)',
                'modified': modified,
                'case_count': case_count
            })
            
    # Sort by modification time (newest first)
    test_files.sort(key=lambda x: x['modified'], reverse=True)
    
    # Get recent test results
    results_files = [f for f in os.listdir('.') if f.startswith('results_') and f.endswith('.csv')]
    results_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)  # Sort by modification time (newest first)
    
    return render_template('index.html', 
                          configs=configs, 
                          test_files=test_files, 
                          results_files=results_files[:5],  # Show only 5 most recent
                          total_results=len(results_files)) # Pass total number for link

@app.route('/all_results')
def all_results():
    # Get all test results
    results_files = [f for f in os.listdir('.') if f.startswith('results_') and f.endswith('.csv')]
    results_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)  # Sort by modification time (newest first)
    
    # Get summary info for each file
    results_info = []
    for file in results_files:
        try:
            # Get file stats
            stats = os.stat(file)
            timestamp = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to read test counts
            try:
                df = pd.read_csv(file)
                total = len(df)
                passed = sum(1 for r in df['Result'] if str(r).startswith('P'))
                failed = total - passed
                if total > 0:
                    pass_rate = round(passed / total * 100, 1)
                else:
                    pass_rate = 0
            except:
                total = 0
                passed = 0
                failed = 0
                pass_rate = 0
            
            # Try to find associated duration - first check in-memory processes
            duration = None
            for run_id, process_data in test_processes.items():
                if process_data.get('results_file') == file and process_data.get('duration') is not None:
                    duration = process_data.get('duration')
                    break
            
            # If not found, check persistent storage
            if duration is None and file in test_durations:
                duration = test_durations[file]
            
            # Add to results info
            results_info.append({
                'file': file,
                'timestamp': timestamp,
                'total': total,
                'passed': passed,
                'failed': failed,
                'pass_rate': pass_rate,
                'duration': duration
            })
        except Exception as e:
            # Skip files that can't be processed
            print(f"Error processing result file {file}: {str(e)}")
            continue
    
    return render_template('all_results.html', results=results_info)

@app.route('/create_test_from_table', methods=['GET', 'POST'])
def create_test_from_table():
    if request.method == 'POST':
        table_data = request.form.get('table_data', '')
        test_name = request.form.get('test_name', f'jira_import_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        check_added = 'check_added' in request.form
        check_removed = 'check_removed' in request.form
        
        if not table_data:
            flash("No table data provided")
            return redirect(url_for('index'))
        
        # Process table data (tab or pipe separated)
        lines = table_data.strip().split('\n')
        test_cases = []
        
        for line in lines:
            # Skip empty lines
            if not line.strip():
                continue
                
            # Try different delimiters
            if '\t' in line:
                parts = line.split('\t')
            else:
                parts = line.split('|')
            
            # Clean up parts
            parts = [p.strip() for p in parts if p.strip()]
            
            if len(parts) >= 2:
                # Assume first part is Year|Model and second is Part
                year_model = parts[0]
                part = parts[1]
                
                # Try to split Year|Model if it contains a space or year indicator
                # First check if this looks like just a year
                if year_model.isdigit() and len(year_model) == 4:
                    year = year_model
                    # If part starts with a year, it might be the model
                    if ' ' in part and part.split(' ')[0].isdigit() and len(part.split(' ')[0]) == 4:
                        model = part.split(' ', 1)[1]
                    else:
                        model = "Unknown Model"  # No model info available
                elif ' ' in year_model:
                    # Try to detect year at beginning
                    year_model_parts = year_model.split(' ', 1)
                    if year_model_parts[0].isdigit() and len(year_model_parts[0]) == 4:
                        year = year_model_parts[0]
                        model = year_model_parts[1]
                    else:
                        # Default split - use current year and whole string as model
                        year = "2024"  # Default year
                        model = year_model
                else:
                    # No spaces and not just a year - assume it's a model with default year
                    year = "2024"  # Default year
                    model = year_model
                
                # Add test case
                expected = "Verify appears in search" if check_added else "Verify no errors in search"
                if check_removed:
                    expected = "ABSENT"  # Special flag for checking part is not present
                
                test_cases.append({
                    'Search': f"{year}|{model}|Part Group|{part}",
                    'Expected': expected
                })
        
        if not test_cases:
            flash("Could not parse any test cases from the table data")
            return redirect(url_for('index'))
        
        # Save to CSV
        filename = f"{test_name}.csv"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        with open(filepath, 'w', newline='') as csvfile:
            fieldnames = ['Search Year|Make Model|Group|Part', 'Expected']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for case in test_cases:
                writer.writerow({
                    'Search Year|Make Model|Group|Part': case['Search'],
                    'Expected': case['Expected']
                })
        
        flash(f"Created {len(test_cases)} test cases in {filename}")
        return redirect(url_for('index'))
    
    return render_template('create_test_from_table.html')

@app.route('/run_test', methods=['POST'])
def run_test():
    platform_type = request.form.get('platform_type', 'web')
    url = request.form.get('url', '')
    username = request.form.get('username', '')
    password = request.form.get('password', '')
    test_file = request.form.get('test_file', 'test_cases.csv')
    headless = 'headless' in request.form
    save_screenshots = 'save_screenshots' in request.form
    wait_time = request.form.get('wait_time', '2.0')
    
    # Check if test file was uploaded
    if 'test_file_upload' in request.files:
        file = request.files['test_file_upload']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            test_file = filepath
    
    # Build command - use the specific script for each platform type
    if platform_type == "app":
        cmd = ["python3", "app4app.py", "--test-set", test_file]
    elif platform_type == "web":
        cmd = ["python3", "app4web.py", "--test-set", test_file]
    elif platform_type == "pro":
        cmd = ["python3", "app4pro.py", "--test-set", test_file]
    elif platform_type == "custom":
        # Custom tester requires URL
        if not url:
            flash("URL is required for custom testing")
            return redirect(url_for('index'))
        cmd = ["python3", "app4custom.py", "--test-set", test_file, "--url", url]
    else:
        cmd = ["python3", "auto_test.py", "--platform", platform_type, "--test-set", test_file]
    
    # Add options (only for non-custom platform types)
    if url and platform_type != "custom":
        cmd.extend(["--url", url])
    if username:
        cmd.extend(["--username", username])
    if password:
        cmd.extend(["--password", password])
    if headless:
        cmd.append("--headless")
    if save_screenshots:
        cmd.append("--save-all-screenshots")
    if wait_time != '2.0':
        cmd.extend(["--wait-time", wait_time])
    
    # Generate a unique ID for this test run
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Start the test process in a separate thread
    threading.Thread(target=run_test_process, args=(run_id, cmd)).start()
    
    flash(f"Test started with ID: {run_id}")
    return redirect(url_for('test_status', run_id=run_id))

def run_test_process(run_id, cmd):
    # Initialize test process data
    test_processes[run_id] = {
        'status': 'running',
        'command': ' '.join(cmd),
        'output': [],
        'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'end_time': None,
        'results_file': None,
        'duration': None
    }
    
    try:
        # Start the process and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Create a watchdog thread to detect if the process stops responding
        threading.Thread(target=process_watchdog, args=(run_id, process), daemon=True).start()
        
        # Read and store output
        for line in process.stdout:
            test_processes[run_id]['output'].append(line.strip())
            
            # Check if line contains results file info
            if "Results saved to " in line:
                results_file = line.split("Results saved to ")[1].strip()
                test_processes[run_id]['results_file'] = results_file
                
            # Mark the process as active to prevent the watchdog from killing it
            test_processes[run_id]['last_update'] = time.time()
        
        # Wait for process to complete
        process.wait()
        
        # Update status based on return code
        if process.returncode == 0:
            test_processes[run_id]['status'] = 'completed'
        else:
            test_processes[run_id]['status'] = 'failed'
        
        # Set end time and calculate duration
        end_time = datetime.now()
        test_processes[run_id]['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate duration
        start_time = datetime.strptime(test_processes[run_id]['start_time'], "%Y-%m-%d %H:%M:%S")
        duration_seconds = (end_time - start_time).total_seconds()
        test_processes[run_id]['duration'] = duration_seconds
        
        # Debug output
        print(f"Test {run_id} completed in {duration_seconds:.1f} seconds")
        
        # Store duration in persistent storage if we have a results file
        if test_processes[run_id].get('results_file'):
            results_file = test_processes[run_id]['results_file']
            test_durations[results_file] = duration_seconds
            try:
                with open(DURATIONS_FILE, 'w') as f:
                    json.dump(test_durations, f)
                print(f"Saved duration for {results_file}: {duration_seconds:.1f} seconds")
            except Exception as e:
                print(f"Error saving test duration: {str(e)}")
        
    except Exception as e:
        test_processes[run_id]['status'] = 'error'
        test_processes[run_id]['output'].append(f"Error: {str(e)}")
        
        # Set end time and calculate duration
        end_time = datetime.now()
        test_processes[run_id]['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate duration
        start_time = datetime.strptime(test_processes[run_id]['start_time'], "%Y-%m-%d %H:%M:%S")
        duration_seconds = (end_time - start_time).total_seconds()
        test_processes[run_id]['duration'] = duration_seconds

def process_watchdog(run_id, process):
    """Monitor a process and force terminate if it stops responding"""
    # Initialize the last update time
    test_processes[run_id]['last_update'] = time.time()
    
    # Check every 15 seconds
    while process.poll() is None:  # While process is still running
        time.sleep(15)
        
        # Check if the process has been updated in the last 2 minutes
        current_time = time.time()
        last_update = test_processes[run_id].get('last_update', 0)
        
        if current_time - last_update > 120:  # 2 minutes with no output
            print(f"Watchdog: Process {run_id} appears to be hung. Terminating.")
            test_processes[run_id]['output'].append("WARNING: Process appears to be hung. Terminated by watchdog.")
            test_processes[run_id]['status'] = 'error'
            
            # Set end time and calculate duration
            end_time = datetime.now()
            test_processes[run_id]['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate duration
            start_time = datetime.strptime(test_processes[run_id]['start_time'], "%Y-%m-%d %H:%M:%S")
            duration_seconds = (end_time - start_time).total_seconds()
            test_processes[run_id]['duration'] = duration_seconds
            
            # Terminate the process
            process.terminate()
            time.sleep(5)
            if process.poll() is None:
                process.kill()  # Force kill if still running
            
            break

@app.route('/test_status/<run_id>')
def test_status(run_id):
    if run_id not in test_processes:
        flash("Test run not found")
        return redirect(url_for('index'))
        
    return render_template('test_status.html', 
                          run_id=run_id, 
                          test_data=test_processes[run_id])

@app.route('/export_log/<run_id>')
def export_log(run_id):
    if run_id not in test_processes:
        flash("Test run not found")
        return redirect(url_for('index'))
    
    # Create log file with test output
    log_content = "\n".join(test_processes[run_id]['output'])
    
    # Create a response with the log as a downloadable file
    from io import BytesIO
    from flask import send_file
    
    bytes_io = BytesIO(log_content.encode('utf-8'))
    return send_file(
        bytes_io,
        as_attachment=True,
        download_name=f"test_log_{run_id}.txt",
        mimetype='text/plain'
    )

@app.route('/api/test_output/<run_id>')
def test_output(run_id):
    if run_id not in test_processes:
        return jsonify({'error': 'Test run not found'}), 404
        
    return jsonify({
        'status': test_processes[run_id]['status'],
        'output': test_processes[run_id]['output'],
        'results_file': test_processes[run_id]['results_file'],
        'duration': test_processes[run_id].get('duration'),
        'start_time': test_processes[run_id].get('start_time'),
        'end_time': test_processes[run_id].get('end_time')
    })

@app.route('/view_config/<config_file>')
def view_config(config_file):
    try:
        with open(config_file, 'r') as f:
            config_content = f.read()
            
        return render_template('view_config.html', 
                              config_file=config_file,
                              config_content=config_content)
    except:
        flash(f"Could not open configuration file: {config_file}")
        return redirect(url_for('index'))
        
@app.route('/view_test_file/<path:test_file>')
def view_test_file(test_file):
    try:
        with open(test_file, 'r') as f:
            test_content = f.read()
        
        # Parse the CSV data to get statistics
        rows = test_content.strip().split('\n')
        header = rows[0]
        test_cases = len(rows) - 1  # Subtract header
        
        # Try to understand the test content for better statistics
        expected_counts = {}
        if test_cases > 0:
            # Try to parse and count different expected results
            for row in rows[1:]:
                # Skip empty rows
                if not row.strip():
                    continue
                    
                # Try to extract expected result - assuming it's the last column
                parts = row.split(',')
                if len(parts) >= 2:
                    expected = parts[-1].strip()
                    expected_counts[expected] = expected_counts.get(expected, 0) + 1
        
        return render_template('view_test_file.html', 
                              test_file=test_file,
                              test_content=test_content,
                              test_cases=test_cases,
                              expected_counts=expected_counts,
                              can_edit=True)
    except Exception as e:
        flash(f"Error opening test file: {str(e)}")
        return redirect(url_for('index'))

@app.route('/delete_test_file/<path:test_file>')
def delete_test_file(test_file):
    try:
        # Check if file exists
        if not os.path.exists(test_file):
            flash(f"Test file {test_file} does not exist")
            return redirect(url_for('index'))
            
        # Delete the file
        os.remove(test_file)
        flash(f"Test file {test_file} deleted successfully")
    except Exception as e:
        flash(f"Error deleting test file: {str(e)}")
        
    return redirect(url_for('index'))

@app.route('/save_test_file', methods=['POST'])
def save_test_file():
    test_file = request.form.get('test_file')
    test_content = request.form.get('test_content')
    
    try:
        # Basic validation - make sure it looks like CSV with a header
        lines = test_content.strip().split('\n')
        if not lines or ',' not in lines[0]:
            flash("Invalid test file format. File should be CSV with a header.")
            return redirect(url_for('view_test_file', test_file=test_file))
        
        # Save to file
        with open(test_file, 'w') as f:
            f.write(test_content)
            
        flash(f"Test file saved to {test_file}")
    except Exception as e:
        flash(f"Error saving test file: {str(e)}")
        
    return redirect(url_for('view_test_file', test_file=test_file))

@app.route('/save_config', methods=['POST'])
def save_config():
    config_file = request.form.get('config_file')
    config_content = request.form.get('config_content')
    
    try:
        # Validate JSON
        json.loads(config_content)
        
        # Save to file
        with open(config_file, 'w') as f:
            f.write(config_content)
            
        flash(f"Configuration saved to {config_file}")
    except json.JSONDecodeError:
        flash("Invalid JSON format. Configuration not saved.")
    except Exception as e:
        flash(f"Error saving configuration: {str(e)}")
        
    return redirect(url_for('view_config', config_file=config_file))

@app.route('/create_config', methods=['GET', 'POST'])
def create_config():
    if request.method == 'POST':
        platform_type = request.form.get('platform_type')
        config_name = request.form.get('config_name')
        
        if not platform_type or not config_name:
            flash("Platform type and name are required")
            return redirect(url_for('create_config'))
        
        # Create filename
        filename = f"config4{platform_type}.json"
        
        # Check if file already exists
        if os.path.exists(filename):
            flash(f"Configuration file {filename} already exists")
            return redirect(url_for('create_config'))
        
        # Create basic config template
        config = {
            "webdriver_options": [
                "--window-size=1200,800"
            ],
            "platforms": [
                {
                    "name": config_name,
                    "type": platform_type,
                    "url": "",
                    "login": {
                        "required": False
                    },
                    "selectors": {
                        "year": "#year",
                        "model": "#model",
                        "part": "",
                        "search_button": ""
                    }
                }
            ]
        }
        
        # Save config file
        try:
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
                
            flash(f"Created new configuration file: {filename}")
            return redirect(url_for('view_config', config_file=filename))
        except Exception as e:
            flash(f"Error creating configuration file: {str(e)}")
            return redirect(url_for('index'))
    
    return render_template('create_config.html')

@app.route('/create_test_file', methods=['GET', 'POST'])
def create_test_file():
    if request.method == 'POST':
        test_name = request.form.get('test_name')
        test_type = request.form.get('test_type')
        
        if not test_name:
            flash("Test name is required")
            return redirect(url_for('create_test_file'))
        
        # Create filename - add .csv if not already included
        if not test_name.endswith('.csv'):
            filename = f"{test_name}.csv"
        else:
            filename = test_name
        
        # Determine location - put custom files in uploads directory
        if test_type == 'upload':
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        else:
            filepath = filename
        
        # Check if file already exists
        if os.path.exists(filepath):
            flash(f"Test file {filepath} already exists")
            return redirect(url_for('create_test_file'))
        
        # Create template content based on test type
        if test_type == 'empty':
            # Just create header row
            content = "Search Year|Make Model|Group|Part,Expected\n"
        elif test_type == 'sample':
            # Create a template with a few sample rows
            content = """Search Year|Make Model|Group|Part,Expected
2023|Honda Civic|Engine|Oil Filter,Verify no errors in search
2022|Toyota Camry|Brakes|Brake Pads,Verify appears in search
2021|Ford F-150|Electrical|Battery,Verify no errors in search
"""
        else:  # upload
            content = """Search Year|Make Model|Group|Part,Expected
2023|Example Make|Part Group|Part Name,Verify no errors in search
"""
        
        # Save test file
        try:
            with open(filepath, 'w', newline='') as f:
                f.write(content)
                
            flash(f"Created new test file: {filepath}")
            return redirect(url_for('view_test_file', test_file=filepath))
        except Exception as e:
            flash(f"Error creating test file: {str(e)}")
            return redirect(url_for('index'))
    
    return render_template('create_test_file.html')

@app.route('/view_results/<results_file>')
def view_results(results_file):
    try:
        results_df = pd.read_csv(results_file)
        
        # Calculate statistics
        total = len(results_df)
        passed = sum(1 for r in results_df['Result'] if str(r).startswith('P'))
        failed = total - passed
        
        if total > 0:
            pass_percent = round(passed / total * 100, 1)
        else:
            pass_percent = 0
            
        # Convert DataFrame to list of dictionaries for template
        results = results_df.to_dict('records')
        
        # Try to find associated duration - first check in-memory processes
        duration = None
        for run_id, process_data in test_processes.items():
            if process_data.get('results_file') == results_file and process_data.get('duration') is not None:
                duration = process_data.get('duration')
                break
        
        # If not found, check persistent storage
        if duration is None and results_file in test_durations:
            duration = test_durations[results_file]
        
        return render_template('view_results.html',
                              results_file=results_file,
                              results=results,
                              total=total,
                              passed=passed,
                              failed=failed,
                              pass_percent=pass_percent,
                              duration=duration)
    except Exception as e:
        flash(f"Could not open results file: {results_file}")
        print(f"Error viewing results: {str(e)}")
        return redirect(url_for('index'))

@app.route('/delete_result/<results_file>')
def delete_result(results_file):
    try:
        os.remove(results_file)
        flash(f"Results file {results_file} deleted")
    except Exception as e:
        flash(f"Error deleting results file: {str(e)}")
    return redirect(url_for('all_results'))

@app.route('/download_results/<results_file>')
def download_results(results_file):
    try:
        return send_file(results_file, as_attachment=True)
    except:
        flash(f"Could not download file: {results_file}")
        return redirect(url_for('index'))

@app.route('/screenshots')
def view_screenshots():
    if not os.path.exists('screenshots'):
        flash("Screenshots directory not found")
        return redirect(url_for('index'))
        
    screenshots = []
    for f in os.listdir('screenshots'):
        if f.endswith('.png'):
            timestamp = os.path.getmtime(os.path.join('screenshots', f))
            date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
            screenshots.append({
                'filename': f,
                'date': date,
                'path': os.path.join('screenshots', f)
            })
    
    # Sort by timestamp (newest first)
    screenshots.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('screenshots.html', screenshots=screenshots)

@app.route('/static/screenshots/<filename>')
def serve_screenshot(filename):
    return send_file(os.path.join('screenshots', filename))

@app.route('/delete_screenshot/<filename>')
def delete_screenshot(filename):
    try:
        os.remove(os.path.join('screenshots', filename))
        flash(f"Screenshot {filename} deleted")
    except Exception as e:
        flash(f"Error deleting screenshot: {str(e)}")
    return redirect(url_for('view_screenshots'))

@app.route('/delete_all_screenshots', methods=['POST'])
def delete_all_screenshots():
    try:
        # Only delete PNG files in screenshots directory
        count = 0
        for f in os.listdir('screenshots'):
            if f.endswith('.png'):
                os.remove(os.path.join('screenshots', f))
                count += 1
        flash(f"Deleted {count} screenshots")
    except Exception as e:
        flash(f"Error deleting screenshots: {str(e)}")
    return redirect(url_for('view_screenshots'))

@app.route('/schedule_test', methods=['GET', 'POST'])
def schedule_test():
    global scheduled_tests
    
    if request.method == 'POST':
        platform_type = request.form.get('platform_type', 'web')
        url = request.form.get('url', '')
        test_file = request.form.get('test_file', 'test_cases.csv')
        headless = 'headless' in request.form
        schedule_type = request.form.get('schedule_type', 'once')
        schedule_date = request.form.get('schedule_date', '')
        schedule_time = request.form.get('schedule_time', '')
        
        if not schedule_date or not schedule_time:
            flash("Schedule date and time are required")
            return redirect(url_for('schedule_test'))
        
        # Parse date and time
        try:
            schedule_datetime = datetime.strptime(f"{schedule_date} {schedule_time}", "%Y-%m-%d %H:%M")
            
            # Make sure it's in the future
            if schedule_datetime < datetime.now():
                flash("Scheduled time must be in the future")
                return redirect(url_for('schedule_test'))
                
            # Create command
            if platform_type == "app":
                cmd = ["python3", "app4app.py", "--test-set", test_file]
            elif platform_type == "web":
                cmd = ["python3", "app4web.py", "--test-set", test_file]
            elif platform_type == "pro":
                cmd = ["python3", "app4pro.py", "--test-set", test_file]
            elif platform_type == "custom":
                if not url:
                    flash("URL is required for custom testing")
                    return redirect(url_for('schedule_test'))
                cmd = ["python3", "app4custom.py", "--test-set", test_file, "--url", url]
            else:
                cmd = ["python3", "auto_test.py", "--platform", platform_type, "--test-set", test_file]
            
            # Add options
            if url and platform_type != "custom":
                cmd.extend(["--url", url])
            if headless:
                cmd.append("--headless")
            
            # Add to scheduled tests
            scheduled_test = {
                'id': len(scheduled_tests) + 1,
                'platform_type': platform_type,
                'test_file': test_file,
                'url': url,
                'headless': headless,
                'schedule_type': schedule_type,
                'schedule_datetime': schedule_datetime,
                'command': ' '.join(cmd),
                'status': 'scheduled'
            }
            
            scheduled_tests.append(scheduled_test)
            flash(f"Test scheduled for {schedule_date} {schedule_time}")
            
            # Start the scheduler if it's not already running
            if len(scheduled_tests) == 1:
                print(f"Starting scheduler thread for test {scheduled_test['id']}")
                scheduler = threading.Thread(target=scheduler_thread, daemon=True)
                scheduler.start()
                print(f"Scheduler thread started: {scheduler.is_alive()}")
                
            return redirect(url_for('view_scheduled_tests'))
        except Exception as e:
            flash(f"Error scheduling test: {str(e)}")
            return redirect(url_for('schedule_test'))
    
    # GET request - show schedule form
    test_files = []
    
    # Check main directory
    for f in os.listdir('.'):
        if f.endswith('.csv') and os.path.isfile(f) and not f.startswith('results_'):
            # Get basic file info
            stats = os.stat(f)
            modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to count test cases
            case_count = 0
            try:
                with open(f, 'r') as file:
                    # Count non-empty lines after header
                    lines = [line for line in file.readlines() if line.strip()]
                    case_count = len(lines) - 1 if len(lines) > 0 else 0
            except:
                pass
                
            test_files.append({
                'path': f,
                'name': f,
                'modified': modified,
                'case_count': case_count
            })
    
    # Check uploads directory
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        if f.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], f)
            
            # Get basic file info
            stats = os.stat(filepath)
            modified = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Try to count test cases
            case_count = 0
            try:
                with open(filepath, 'r') as file:
                    # Count non-empty lines after header
                    lines = [line for line in file.readlines() if line.strip()]
                    case_count = len(lines) - 1 if len(lines) > 0 else 0
            except:
                pass
                
            test_files.append({
                'path': filepath,
                'name': f + ' (uploaded)',
                'modified': modified,
                'case_count': case_count
            })
            
    # Sort by modification time (newest first)
    test_files.sort(key=lambda x: x['modified'], reverse=True)
    
    # Get available configuration files
    config_files = [f for f in os.listdir('.') if f.startswith('config4') and f.endswith('.json')]
    configs = []
    
    for cf in config_files:
        try:
            with open(cf, 'r') as f:
                config = json.load(f)
                platform_type = cf.replace('config4', '').replace('.json', '')
                platform_name = config['platforms'][0]['name'] if config.get('platforms') else platform_type
                configs.append({
                    'file': cf,
                    'type': platform_type,
                    'name': platform_name
                })
        except:
            # Skip invalid config files
            continue
    
    return render_template('schedule_test.html', configs=configs, test_files=test_files)

@app.route('/view_scheduled_tests')
def view_scheduled_tests():
    # Map scheduled test IDs to run_ids if available
    for test in scheduled_tests:
        if test.get('status') == 'running' and not test.get('run_id'):
            # Look for a running test process with matching command
            for run_id, process_data in test_processes.items():
                if process_data.get('command') == test.get('command'):
                    test['run_id'] = run_id
                    break
    
    return render_template('view_scheduled_tests.html', scheduled_tests=scheduled_tests)

@app.route('/cancel_scheduled_test/<int:test_id>')
def cancel_scheduled_test(test_id):
    global scheduled_tests
    
    # Find and remove the scheduled test
    for i, test in enumerate(scheduled_tests):
        if test['id'] == test_id:
            if test['status'] == 'scheduled':
                del scheduled_tests[i]
                flash(f"Scheduled test {test_id} canceled")
            else:
                flash(f"Cannot cancel test {test_id} - already {test['status']}")
            break
    else:
        flash(f"Scheduled test {test_id} not found")
    
    return redirect(url_for('view_scheduled_tests'))

def scheduler_thread():
    """Background thread that checks and runs scheduled tests"""
    global scheduled_tests
    
    print("Scheduler thread started")
    
    while True:
        # Check if we have any scheduled tests
        if not scheduled_tests:
            # Sleep for 30 seconds and check again
            time.sleep(30)
            continue
        
        now = datetime.now()
        print(f"Scheduler check: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check each scheduled test
        for test in scheduled_tests:
            # Debug info
            test_time = test['schedule_datetime']
            time_diff = (test_time - now).total_seconds()
            print(f"Test {test['id']} status: {test['status']}, scheduled for: {test_time.strftime('%Y-%m-%d %H:%M:%S')}, diff: {time_diff:.1f} seconds")
            
            # Start new scheduled tests
            should_run = False
            if test['status'] == 'scheduled':
                time_diff = (test_time - now).total_seconds()
                should_run = time_diff <= 0
                
                if should_run:
                    # Time to run this test
                    print(f"Running scheduled test {test['id']} (time diff: {time_diff:.1f} seconds)")
                    test['status'] = 'running'
                    
                    # Start in a separate thread
                    runner = threading.Thread(target=run_scheduled_test, args=(test,), daemon=True)
                    runner.start()
                    print(f"Test runner thread started: {runner.is_alive()}")
            
            # Update completed tests with results files
            elif test['status'] in ['completed', 'failed', 'error'] and test.get('run_id') and not test.get('results_file'):
                # Check if there's a results file in the test process data
                if test['run_id'] in test_processes and test_processes[test['run_id']].get('results_file'):
                    test['results_file'] = test_processes[test['run_id']]['results_file']
        
        # Sleep for 10 seconds before checking again
        time.sleep(10)

def run_scheduled_test(test):
    """Run a scheduled test"""
    # Check if test file exists
    test_file = test.get('test_file')
    if test_file and not os.path.exists(test_file):
        print(f"Error: Test file {test_file} not found")
        test['status'] = 'error'
        return
    
    # Parse the command string back into a list
    cmd = test['command'].split()
    print(f"Executing scheduled test command: {test['command']}")
    
    # Generate a unique ID for this test run
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Generated run_id: {run_id}")
    
    # Store the run_id in the test
    test['run_id'] = run_id
    
    # Initialize test process data
    test_processes[run_id] = {
        'status': 'running',
        'command': test['command'],
        'output': [],
        'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'end_time': None,
        'results_file': None,
        'duration': None
    }
    
    try:
        # Start the process and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Create a watchdog thread to detect if the process stops responding
        threading.Thread(target=process_watchdog, args=(run_id, process), daemon=True).start()
        
        # Read and store output
        for line in process.stdout:
            test_processes[run_id]['output'].append(line.strip())
            
            # Check if line contains results file info
            if "Results saved to " in line:
                results_file = line.split("Results saved to ")[1].strip()
                test_processes[run_id]['results_file'] = results_file
                
            # Mark the process as active to prevent the watchdog from killing it
            test_processes[run_id]['last_update'] = time.time()
        
        # Wait for process to complete
        process.wait()
        
        # Update status based on return code
        if process.returncode == 0:
            test_processes[run_id]['status'] = 'completed'
            test['status'] = 'completed'
        else:
            test_processes[run_id]['status'] = 'failed'
            test['status'] = 'failed'
        
        # Set end time and calculate duration
        end_time = datetime.now()
        test_processes[run_id]['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate duration
        start_time = datetime.strptime(test_processes[run_id]['start_time'], "%Y-%m-%d %H:%M:%S")
        duration_seconds = (end_time - start_time).total_seconds()
        test_processes[run_id]['duration'] = duration_seconds
        
        # Store duration in persistent storage if we have a results file
        if test_processes[run_id].get('results_file'):
            results_file = test_processes[run_id]['results_file']
            test_durations[results_file] = duration_seconds
            try:
                with open(DURATIONS_FILE, 'w') as f:
                    json.dump(test_durations, f)
                print(f"Saved duration for {results_file}: {duration_seconds:.1f} seconds")
            except Exception as e:
                print(f"Error saving test duration: {str(e)}")
        
    except Exception as e:
        test_processes[run_id]['status'] = 'error'
        test_processes[run_id]['output'].append(f"Error: {str(e)}")
        
        # Set end time and calculate duration
        end_time = datetime.now()
        test_processes[run_id]['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate duration
        start_time = datetime.strptime(test_processes[run_id]['start_time'], "%Y-%m-%d %H:%M:%S")
        duration_seconds = (end_time - start_time).total_seconds()
        test_processes[run_id]['duration'] = duration_seconds
        
        # Store duration in persistent storage if we have a results file
        if test_processes[run_id].get('results_file'):
            results_file = test_processes[run_id]['results_file']
            test_durations[results_file] = duration_seconds
            try:
                with open(DURATIONS_FILE, 'w') as f:
                    json.dump(test_durations, f)
                print(f"Saved duration for {results_file}: {duration_seconds:.1f} seconds")
            except Exception as e:
                print(f"Error saving test duration: {str(e)}")
        
        test['status'] = 'error'
        print(f"Error in scheduled test {test['id']}: {str(e)}")

if __name__ == '__main__':
    # Start the scheduler thread if there are scheduled tests
    if scheduled_tests:
        print(f"Starting scheduler thread on app startup with {len(scheduled_tests)} tests")
        threading.Thread(target=scheduler_thread, daemon=True).start()
    
    # Run the app
    app.run(debug=True, host='0.0.0.0', port=5000)  # Reloader enabled for development