# Automated HTML Testing

This project provides automated testing tools for car parts websites and applications. It allows you to test search functionality, verify results, and identify issues in the UI.

## Overview

The system consists of:

1. **Original Scripts** - Specialized testing scripts for different platforms:
   - `app4web.py` - For testing web interfaces
   - `app4pro.py` - For testing professional platforms with login
   - `app4app.py` - For testing desktop applications 

2. **Unified Solution** - Various ways to run the tests:
   - `auto_test.py` - Unified command-line script for all platforms
   - `app.py` - Web interface using Flask (recommended)
   - `auto_test_gui.py` - Desktop GUI (requires tkinter)

3. **Configuration** - Platform-specific configuration files:
   - `config4web.json` - Configuration for web testing
   - `config4pro.json` - Configuration for professional platform testing  
   - `config4app.json` - Configuration for desktop app testing

## Getting Started

### Prerequisites

- Python 3.x
- Required packages (install via `pip install -r requirements.txt`):
  - selenium
  - pandas
  - webdriver_manager
  - flask (for web interface)
  - flask-wtf (for web interface)
  - tkinter (for desktop GUI, optional)

### Running Tests via Web Interface (Recommended)

The Flask web interface provides an easy way to run tests from any browser:

1. Launch the web server:
   ```
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

3. In the web interface:
   - Select the platform type (web, pro, or app)
   - Enter the website URL you want to test (optional, overrides config)
   - Provide login credentials if required
   - Select your test cases file or upload a new one
   - Configure test options (headless mode, screenshots, etc.)
   - Click "Run Test" to begin testing

4. View real-time test progress, results, and screenshots in the web interface

### Running Tests via Command Line

For automation or scripting, use the command-line interface:

```
python auto_test.py --platform web --test-set test_cases.csv
```

Additional options:
- `--platform` - Platform type: web, pro, or app (default: web)
- `--url` - Override URL from config file
- `--username` - Username for login (if required)
- `--password` - Password for login (if required)
- `--headless` - Run in headless mode (no browser UI)
- `--save-all-screenshots` - Save screenshots for all steps, not just errors
- `--wait-time` - Time to wait between actions in seconds (default: 2.0)

### Running Tests via Desktop GUI (Requires tkinter)

If you prefer a desktop application:

1. Launch the GUI:
   ```
   python auto_test_gui.py
   ```

2. In the Test Setup tab:
   - Enter the website URL you want to test
   - Provide login credentials if required
   - Select your test cases file (CSV format)
   - Choose platform type (web, pro, or app)
   - Configure test options (headless mode, screenshots, etc.)

3. Click "Run Tests" to begin testing

## Test Case Format

Test cases should be in CSV format with the following structure:

```
Search Year|Make Model|Group|Part,Expected
2023|Alfa Tonale|Air & Fuel|Fuel Injector Rail,Verify no errors in search
2023|Alfa Tonale|Body|Hood Release Cable,Verify no errors in search
```

The format uses pipe characters to separate:
- Year
- Make Model 
- Group (component group/category)
- Part (specific part name)

## Configuration Files

Each platform has its own configuration file (config4web.json, config4pro.json, config4app.json) with the following structure:

```json
{
  "webdriver_options": [
    "--window-size=1200,800"
  ],
  "platforms": [
    {
      "name": "platform_name",
      "type": "web|pro|app",
      "url": "https://example.com",
      "login": {
        "required": false,
      },
      "selectors": {
        "year": "#year",
        "model": "#model",
        "part": "selector_for_part",
        "search_button": "selector_for_search_button"
      }
    }
  ]
}
```

For platforms requiring login, add these fields under the platform entry:

```json
"requires_login": true,
"username": "your_username",
"password": "your_password",
"login_selectors": {
  "username_field": "#username",
  "password_field": "#password",
  "login_button": "#login_button"
}
```

## Features

- **Robust Element Interaction**: Multiple fallback methods to click elements
- **Flexible Search Strategies**: Adaptive ways to find elements with different structures
- **Comprehensive Error Handling**: Detailed error reporting with screenshots
- **Dropdown Validation**: Checks for issues like duplicate entries and order problems
- **Results Verification**: Validates search results contain expected information
- **Screenshot Capture**: Visual verification of test steps
- **Web Interface**: Modern, responsive interface accessible from any device
- **Real-time Test Monitoring**: Watch test progress in real time via the web interface

## Results

Test results are saved as CSV files with timestamp (results_YYYYMMDD_HHMMSS.csv) containing:
- Search query that was tested
- Expected result
- Actual result (Pass/Fail with details)

If dropdown issues are found, they are logged in a separate file (dropdown_issues_YYYYMMDD_HHMMSS.txt).

## Customizing for New Websites

To adapt the tests for a new website:

1. Create a new configuration file or modify an existing one
2. Update the selectors section with appropriate CSS selectors for the site
3. Run initial tests with `--save-all-screenshots` to verify element identification
4. Adjust selectors as needed based on test results

## Web Interface Features

The Flask web interface provides:

- **Dashboard**: View available configs, test files, and recent results
- **Test Runner**: Configure and run tests with real-time progress tracking
- **Results Viewer**: Visualize test results with pass/fail statistics
- **Configuration Editor**: Edit configuration files directly in the browser
- **Screenshot Gallery**: Browse all screenshots captured during testing
- **Downloads**: Export and download test results