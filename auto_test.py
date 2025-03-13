import json
import pandas as pd
import argparse
import os
import time
import sys
from datetime import datetime

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    StaleElementReferenceException,
    ElementNotInteractableException,
    ElementClickInterceptedException
)

# Command line arguments
parser = argparse.ArgumentParser(description="Unified Car Parts Automation Test Script")
parser.add_argument("--test-set", help="Path to test cases CSV file", default="test_cases.csv")
parser.add_argument("--platform", help="Platform to test: web, pro, or app", default="web")
parser.add_argument("--url", help="Override the URL in the config file")
parser.add_argument("--username", help="Username for login")
parser.add_argument("--password", help="Password for login")
parser.add_argument("--headless", action="store_true", help="Run tests in headless mode")
parser.add_argument("--save-all-screenshots", action="store_true", 
                    help="Save screenshots for all steps, not just errors")
parser.add_argument("--wait-time", type=float, default=2.0,
                    help="Wait time between actions (default: 2.0)")
args = parser.parse_args()

# Set up global variables
PLATFORM = args.platform
WAIT_TIME = args.wait_time
SAVE_ALL_SCREENSHOTS = args.save_all_screenshots

# Make a directory for screenshots if it doesn't exist
os.makedirs("screenshots", exist_ok=True)

# Load configuration
config_file = f"config4{PLATFORM}.json"
try:
    with open(config_file, 'r') as f:
        config = json.load(f)
    print(f"Loaded configuration from {config_file}")
except FileNotFoundError:
    print(f"Configuration file {config_file} not found. Creating default configuration.")
    # Create a default configuration
    config = {
        "webdriver_options": ["--window-size=1200,800"],
        "platforms": [
            {
                "name": f"default_{PLATFORM}",
                "type": PLATFORM,
                "url": args.url or "https://example.com",
                "login": {"required": False}
            }
        ]
    }
    # Save default config
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

# Override URL if provided via command line
if args.url:
    print(f"Overriding URL with command line parameter: {args.url}")
    config["platforms"][0]["url"] = args.url

# Set up Chrome with configured options
chrome_options = Options()
for option in config["webdriver_options"]:
    chrome_options.add_argument(option)

# Add headless mode if requested
if args.headless:
    print("Running in headless mode")
    chrome_options.add_argument("--headless")

# Start browser with WebDriver Manager for automatic driver installation
print("Starting Chrome browser...")
try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    print("Chrome browser started successfully")
except Exception as e:
    print(f"Error starting Chrome browser: {str(e)}")
    print("Attempting to start with default Chrome driver...")
    driver = webdriver.Chrome(options=chrome_options)

# Create a function to save debug info
def save_debug_info(prefix, always_save=False, error_occurred=False):
    """Save screenshot and HTML source for debugging"""
    if error_occurred or always_save or SAVE_ALL_SCREENSHOTS:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"screenshots/{prefix}_{timestamp}"
        
        # Save screenshot
        driver.save_screenshot(f"{filename_base}.png")
        
        # Save HTML source
        with open(f"{filename_base}.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        
        print(f"Saved debug info to {filename_base}.png and {filename_base}.html")
        return filename_base
    else:
        return None

# Try multiple methods to click an element
def try_click(element, description):
    """Try multiple methods to click an element"""
    try:
        # Method 1: Standard click
        element.click()
        print(f"Clicked {description} using standard click")
        return True
    except (ElementNotInteractableException, ElementClickInterceptedException) as e:
        print(f"Standard click failed: {str(e)}")
        try:
            # Method 2: JavaScript click
            driver.execute_script("arguments[0].click();", element)
            print(f"Clicked {description} using JavaScript")
            return True
        except Exception as e:
            print(f"JavaScript click failed: {str(e)}")
            try:
                # Method 3: ActionChains
                actions = ActionChains(driver)
                actions.move_to_element(element).click().perform()
                print(f"Clicked {description} using ActionChains")
                return True
            except Exception as e:
                print(f"Could not click {description}: {str(e)}")
                return False

# Handle login if required
def handle_login(platform):
    """Handle login for sites that require authentication"""
    if platform.get("requires_login", False) or (args.username and args.password):
        try:
            username = args.username or platform.get("username", "")
            password = args.password or platform.get("password", "")
            
            if not username or not password:
                print("Login credentials required but not provided")
                return False
                
            print(f"Logging in to {platform['name']}...")
            
            # Wait for the login page to load
            time.sleep(WAIT_TIME * 2)
            
            # Take a screenshot to see the login page
            save_debug_info("login_page", always_save=True)
            
            # Find and fill username field
            try:
                username_selector = platform.get("login_selectors", {}).get("username_field", "#username")
                username_field = WebDriverWait(driver, WAIT_TIME).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, username_selector))
                )
                username_field.clear()
                username_field.send_keys(username)
                print(f"Entered username: {username}")
                
                # Press Enter after username (sometimes required)
                username_field.send_keys(Keys.TAB)
                time.sleep(WAIT_TIME/2)
            except Exception as e:
                print(f"Error entering username: {str(e)}")
                
                # Try finding username field by other means
                try:
                    # Try common username field attributes
                    username_fields = driver.find_elements(By.XPATH, 
                        "//input[@type='text' and (contains(@name, 'user') or contains(@id, 'user') or contains(@placeholder, 'user'))]")
                    
                    if username_fields and username_fields[0].is_displayed():
                        username_fields[0].clear()
                        username_fields[0].send_keys(username)
                        print(f"Found username field by attribute search")
                    else:
                        raise Exception("Could not find username field")
                except Exception as e2:
                    print(f"Could not find username field: {str(e2)}")
                    return False
            
            # Find and fill password field
            try:
                password_selector = platform.get("login_selectors", {}).get("password_field", "#password")
                password_field = WebDriverWait(driver, WAIT_TIME).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, password_selector))
                )
                password_field.clear()
                password_field.send_keys(password)
                print("Entered password")
            except Exception as e:
                print(f"Error entering password: {str(e)}")
                
                # Try finding password field by other means
                try:
                    # Try common password field attributes
                    password_fields = driver.find_elements(By.XPATH, "//input[@type='password']")
                    
                    if password_fields and password_fields[0].is_displayed():
                        password_fields[0].clear()
                        password_fields[0].send_keys(password)
                        print(f"Found password field by type")
                    else:
                        raise Exception("Could not find password field")
                except Exception as e2:
                    print(f"Could not find password field: {str(e2)}")
                    return False
                    
            # Click login button
            try:
                login_button_selector = platform.get("login_selectors", {}).get("login_button", 
                    "button[type='submit'], input[type='submit'], .login-button, #login-button")
                
                login_buttons = driver.find_elements(By.CSS_SELECTOR, login_button_selector)
                
                if login_buttons:
                    for button in login_buttons:
                        if button.is_displayed():
                            if try_click(button, "login button"):
                                break
                else:
                    # Try submitting the form instead
                    password_field.send_keys(Keys.RETURN)
                    print("Submitted login form with Enter key")
            except Exception as e:
                print(f"Error clicking login button: {str(e)}")
                return False
            
            # Wait for login to complete
            time.sleep(WAIT_TIME * 2)
            
            # Check if login was successful
            current_url = driver.current_url
            if "login" in current_url.lower():
                print(f"Still on login page after attempt: {current_url}")
                save_debug_info("login_failed", always_save=True)
                return False
            else:
                print(f"Login successful! Redirected to: {current_url}")
                return True
        except Exception as e:
            print(f"Login error: {str(e)}")
            save_debug_info("login_error", error_occurred=True)
            return False
    else:
        # No login required
        return True

# Check for issues in dropdown menus
def check_dropdown_issues(select_element):
    """Check for duplicates and ordering issues in a dropdown menu"""
    dropdown_issues = []
    options = [option.text for option in select_element.options if option.text.strip()]
    
    # Check for duplicates
    seen = set()
    for option in options:
        if option in seen and option != "Select Part":
            dropdown_issues.append(f"Duplicate dropdown option found: {option}")
        seen.add(option)
    
    # Check alphabetical order (skipping any "Select" option)
    sortable_options = [opt for opt in options if not opt.startswith("Select")]
    sorted_options = sorted(sortable_options)
    if sortable_options != sorted_options:
        # Find some examples of out-of-order items
        for i in range(len(sortable_options) - 1):
            if sortable_options[i] > sortable_options[i+1]:
                dropdown_issues.append(f"Dropdown options out of order: '{sortable_options[i]}' should come after '{sortable_options[i+1]}'")
                # Limit to a few examples
                if len([i for i in dropdown_issues if "out of order" in i]) >= 3:
                    break
    
    return dropdown_issues

# Handle errors that occur during testing
def handle_test_error(e, test_data, index):
    """Handle test errors, classify them, and document appropriately"""
    error_type = type(e).__name__
    error_message = str(e)
    
    # Classify error types
    if isinstance(e, NoSuchElementException):
        error_category = "Element Not Found"
    elif isinstance(e, TimeoutException):
        error_category = "Timeout"
    elif isinstance(e, StaleElementReferenceException):
        error_category = "Page Changed"
    elif isinstance(e, ElementNotInteractableException):
        error_category = "Element Not Interactable"
    else:
        error_category = "General Error"
    
    # Log detailed error information
    print(f"ERROR ({error_category}): {error_message}")
    
    # Save error screenshots and HTML
    debug_file = save_debug_info(f"error_{error_category}_case_{index+1}", error_occurred=True)
    print(f"Saved error debug info to {debug_file}")
    
    # Capture additional diagnostic information
    try:
        current_url = driver.current_url
        page_title = driver.title
        print(f"Error occurred at: {page_title} - {current_url}")
    except:
        print("Could not get current page details")
    
    # Store failure result with categorization
    search_details = test_data.get('Search Year|Make Model|Group|Part', "")
    expected = test_data.get('Expected', "")
    
    return {
        'Search': search_details,
        'Expected': expected,
        'Result': f"F - {error_category}: {error_message[:100]}..." if len(error_message) > 100 else f"F - {error_category}: {error_message}"
    }

# Handles searching with a web-specific approach
def web_search(test_data, platform):
    """Perform search using web platform approach"""
    try:
        # Parse test data
        parts = test_data['Search Year|Make Model|Group|Part'].split('|')
        year = parts[0]
        model = parts[1]
        part_group = parts[2] if len(parts) > 2 else ""
        part = parts[3] if len(parts) > 3 else ""
        
        # Take a screenshot of the initial page
        save_debug_info("initial_page", always_save=True)
        
        # ===== 1. Click and set Year =====
        print(f"Selecting year: {year}")
        
        # First click the year dropdown (web specific)
        year_dropdown = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#yearSelect"))
        )
        try_click(year_dropdown, "year dropdown")
        time.sleep(WAIT_TIME)
        
        # Now find and click the specific year
        try:
            # Take a screenshot to see the dropdown options
            save_debug_info("year_dropdown_open", always_save=True)
            
            year_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{year}')]")
            
            if year_elements:
                for elem in year_elements:
                    if elem.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        time.sleep(WAIT_TIME/2)
                        try_click(elem, f"year {year}")
                        print(f"Clicked year: {year}")
                        break
            else:
                # If we can't find direct links, look for input fields
                year_inputs = driver.find_elements(By.XPATH, "//input[@type='text']")
                for input_elem in year_inputs:
                    if input_elem.is_displayed():
                        input_elem.clear()
                        input_elem.send_keys(year)
                        input_elem.send_keys(Keys.RETURN)
                        print(f"Entered year {year} in input field")
                        time.sleep(WAIT_TIME)
                        break
                else:
                    # Try JavaScript to find and click anything with the year
                    driver.execute_script("""
                        var yearElements = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.includes('""" + year + """'));
                        for (var i=0; i < yearElements.length; i++) {
                            if (yearElements[i].click) {
                                yearElements[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    print("Used JavaScript to click year element")
        except Exception as e:
            print(f"Error selecting year: {str(e)}")
        
        # Save a screenshot after year selection attempt
        save_debug_info("after_year_selection", always_save=True)
        
        # ===== 2. Click and set Make/Model =====
        # First extract make and model separately
        model_parts = model.split()
        if len(model_parts) >= 2:
            make = model_parts[0]  # First word is likely the make
            model_name = ' '.join(model_parts[1:])  # Rest is the model
        else:
            make = model  # If only one word, assume it's both make and model
            model_name = ""
        
        print(f"Selecting make: {make}")
        
        # First click the vehicle dropdown
        try:
            vehicle_dropdown = WebDriverWait(driver, WAIT_TIME).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#vehicleSelect"))
            )
            try_click(vehicle_dropdown, "make dropdown")
            time.sleep(WAIT_TIME)
            
            # Try to find and click the make
            make_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{make}')]")
            if make_elements:
                for elem in make_elements:
                    if elem.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        time.sleep(WAIT_TIME/2)
                        try_click(elem, f"make {make}")
                        print(f"Clicked make: {make}")
                        break
            else:
                # Use JavaScript to find and click the make
                driver.execute_script("""
                    var elements = Array.from(document.querySelectorAll('*'));
                    for (var i=0; i < elements.length; i++) {
                        if (elements[i].textContent.indexOf('""" + make + """') >= 0 && 
                            elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                            elements[i].scrollIntoView(true);
                            elements[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                print(f"Used JavaScript to click make: {make}")
        except Exception as e:
            print(f"Error selecting make: {str(e)}")
        
        # Save a screenshot after make selection
        save_debug_info("after_make_selection", always_save=True)
        
        # Now select model if needed
        if model_name:
            print(f"Selecting model: {model_name}")
            try:
                # Try to find and click the model
                model_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{model_name}')]")
                if model_elements:
                    for elem in model_elements:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(WAIT_TIME/2)
                            try_click(elem, f"model {model_name}")
                            print(f"Clicked model: {model_name}")
                            break
                else:
                    # Use JavaScript to find and click the model
                    driver.execute_script("""
                        var elements = Array.from(document.querySelectorAll('*'));
                        for (var i=0; i < elements.length; i++) {
                            if (elements[i].textContent.indexOf('""" + model_name + """') >= 0 && 
                                elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                                elements[i].scrollIntoView(true);
                                elements[i].click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    print(f"Used JavaScript to click model: {model_name}")
            except Exception as e:
                print(f"Error selecting model: {str(e)}")
        
        # Save a screenshot after model selection
        save_debug_info("after_model_selection", always_save=True)
        
        # ===== 3. Select part group if needed =====
        if part_group:
            print(f"Selecting part group: {part_group}")
            
            try:
                # Try to find any element containing the part group text
                part_group_elements = driver.find_elements(By.XPATH, 
                                                    f"//a[contains(text(), '{part_group}')] | //button[contains(text(), '{part_group}')]")
                
                if part_group_elements:
                    for elem in part_group_elements:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            try_click(elem, f"part group {part_group}")
                            print(f"Clicked part group: {part_group}")
                            break
                else:
                    # Try to find it by partial text
                    part_words = [w for w in part_group.split() if len(w) > 3]
                    for word in part_words:
                        elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{word}')] | //button[contains(text(), '{word}')]")
                        if elements:
                            for elem in elements:
                                if elem.is_displayed():
                                    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                                    try_click(elem, f"part group by keyword {word}")
                                    print(f"Clicked part group by keyword: {word}")
                                    break
                            break
            except Exception as e:
                print(f"Error selecting part group: {str(e)}")
        
        # Save a screenshot after part group selection
        save_debug_info("after_part_group_selection", always_save=True)
        
        # ===== 4. Select Part =====
        print(f"Selecting part: {part}")
        
        # Extract the main part name and qualifier if present
        part_main = part
        part_qualifier = ""
        if '(' in part:
            part_main = part.split('(')[0].strip()
            part_qualifier = part.split('(')[1].split(')')[0].strip()
            print(f"Split part into main: '{part_main}' and qualifier: '{part_qualifier}'")
        
        # Wait longer for part options to become visible
        time.sleep(WAIT_TIME)
        
        # Take a screenshot to see available parts
        save_debug_info("before_part_selection", always_save=True)
        
        # Try a more comprehensive approach to find and click the part
        part_found = False
        
        # First, try to find and click the main part name
        try:
            # Exact matches for main part
            main_exact_xpath = f"//a[normalize-space(text())='{part_main}'] | //div[normalize-space(text())='{part_main}'] | //span[normalize-space(text())='{part_main}'] | //button[normalize-space(text())='{part_main}']"
            main_exact_matches = driver.find_elements(By.XPATH, main_exact_xpath)
            
            if main_exact_matches:
                for elem in main_exact_matches:
                    if elem.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                        try_click(elem, f"exact main part match: {part_main}")
                        print(f"Clicked exact main part match: {part_main}")
                        part_found = True
                        selected_part = part_main
                        break
            
            # If main part wasn't found, try partial matches
            if not part_found:
                main_contains_xpath = f"//a[contains(text(),'{part_main}')] | //div[contains(text(),'{part_main}')] | //span[contains(text(),'{part_main}')] | //button[contains(text(),'{part_main}')]"
                main_contains_matches = driver.find_elements(By.XPATH, main_contains_xpath)
                
                if main_contains_matches:
                    for elem in main_contains_matches:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            try_click(elem, f"partial main part match: {elem.text}")
                            print(f"Clicked partial main part match: {elem.text}")
                            part_found = True
                            selected_part = elem.text
                            break
            
            # If we have a qualifier and main part was found, try to find the qualifier next
            if part_found and part_qualifier:
                # Take a screenshot after clicking main part
                save_debug_info("after_main_part_selection", always_save=True)
                
                time.sleep(WAIT_TIME)  # Wait for any submenus to appear
                
                # Try to find and click the qualifier
                qualifier_xpath = f"//a[contains(text(),'{part_qualifier}')] | //div[contains(text(),'{part_qualifier}')] | //span[contains(text(),'{part_qualifier}')] | //button[contains(text(),'{part_qualifier}')]"
                qualifier_matches = driver.find_elements(By.XPATH, qualifier_xpath)
                
                if qualifier_matches:
                    for elem in qualifier_matches:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            try_click(elem, f"qualifier match: {elem.text}")
                            print(f"Clicked qualifier match: {elem.text}")
                            selected_part = f"{selected_part} ({elem.text})"
                            break
                else:
                    print(f"Could not find qualifier '{part_qualifier}', continuing with main part only")
            
            # If we still haven't found the part, try JavaScript with the full part name
            if not part_found:
                driver.execute_script("""
                    var elements = Array.from(document.querySelectorAll('*'));
                    for (var i=0; i < elements.length; i++) {
                        if (elements[i].textContent.indexOf('""" + part + """') >= 0 && 
                            elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                            elements[i].scrollIntoView(true);
                            elements[i].click();
                            return true;
                        }
                    }
                    return false;
                """)
                print(f"Used JavaScript to try clicking part: {part}")
                selected_part = part
                part_found = True
        except Exception as e:
            print(f"Error during part selection: {str(e)}")
            selected_part = part  # Use original part name for verification
        
        if not part_found:
            print(f"WARNING: Could not find part: {part} - continuing anyway")
            selected_part = part  # Use original part name for verification
        
        # Save a screenshot after part selection
        save_debug_info("after_part_selection", always_save=True)
        
        # ===== 5. Enter ZIP code =====
        print("Entering ZIP code: 41094")
        
        try:
            # Try to find zip code input field
            zip_input = driver.find_element(By.XPATH, 
                                          "//input[@type='text' and (contains(@placeholder, 'zip') or contains(@name, 'zip') or @maxlength='5')]")
            
            zip_input.clear()
            zip_input.send_keys("41094")
            print("Entered ZIP code: 41094")
            time.sleep(WAIT_TIME/2)
        except:
            print("Could not find ZIP code field, continuing without ZIP")
        
        # ===== 6. Click Search button =====
        print("Clicking search button")
        search_button_clicked = False
        
        # Try different approaches to find and click the search button
        try:
            # First try specific selectors
            search_selectors = [
                "body > form > input.search",
                "input[type='submit']",
                "button[type='submit']", 
                "input[value='Search']", 
                "button:contains('Search')"
            ]
            
            for selector in search_selectors:
                try:
                    search_buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in search_buttons:
                        if button.is_displayed():
                            if try_click(button, f"search button with selector {selector}"):
                                print(f"Clicked search button with selector: {selector}")
                                search_button_clicked = True
                                break
                    if search_button_clicked:
                        break
                except:
                    continue
                    
            # If no button found, try a broader approach
            if not search_button_clicked:
                search_elements = driver.find_elements(By.XPATH, 
                    "//input[@type='submit'] | //button[@type='submit'] | //input[@value='Search'] | //button[contains(text(), 'Search')]")
                
                for element in search_elements:
                    if element.is_displayed():
                        if try_click(element, "search button by text/type"):
                            print("Clicked search button by text/type")
                            search_button_clicked = True
                            break
            
            # If still no success, try to submit any form
            if not search_button_clicked:
                forms = driver.find_elements(By.TAG_NAME, "form")
                for form in forms:
                    try:
                        form.submit()
                        print("Submitted form")
                        search_button_clicked = True
                        break
                    except:
                        continue
                        
            if not search_button_clicked:
                # Last resort: JavaScript approach
                driver.execute_script("""
                    // Try to find a search button or input
                    var searchElements = [
                        ...document.querySelectorAll('input[type="submit"]'),
                        ...document.querySelectorAll('button[type="submit"]'),
                        ...document.querySelectorAll('button'),
                        ...document.querySelectorAll('a')
                    ];
                    
                    // Filter to visible elements with search-related text or attributes
                    for (let elem of searchElements) {
                        if (elem.offsetWidth > 0 && elem.offsetHeight > 0) {
                            let text = (elem.textContent || '').toLowerCase();
                            let value = (elem.value || '').toLowerCase();
                            
                            if (text.includes('search') || value.includes('search')) {
                                elem.click();
                                return true;
                            }
                        }
                    }
                    
                    // If all else fails, submit the first form
                    let forms = document.forms;
                    if (forms.length > 0) {
                        forms[0].submit();
                        return true;
                    }
                    
                    return false;
                """)
                print("Used JavaScript to find and click search button")
                search_button_clicked = True
        except Exception as e:
            print(f"Error clicking search button: {str(e)}")
            raise Exception(f"Could not click search button: {str(e)}")
            
        # Wait for results page to load
        time.sleep(WAIT_TIME * 2)
        
        # Save screenshot of results
        save_debug_info("initial_results", always_save=True)
        
        # Check if we're on an interchange page
        page_text = driver.find_element(By.TAG_NAME, "body").text
        is_interchange_page = "interchange" in page_text.lower() or (
            "search using" in page_text.lower() and "model" in page_text.lower()
        )
        
        print(f"Is this an interchange page? {'Yes' if is_interchange_page else 'No'}")
        
        if is_interchange_page:
            print("On interchange page - clicking search button again")
            
            try:
                # Try to find and click the search button on interchange page
                search_elements = driver.find_elements(By.XPATH, 
                    "//input[@type='submit'] | //button[@type='submit'] | //input[@value='Search'] | //button[contains(text(), 'Search')]")
                
                for element in search_elements:
                    if element.is_displayed():
                        if try_click(element, "interchange search button"):
                            print("Clicked interchange search button")
                            time.sleep(WAIT_TIME * 2)
                            break
            except Exception as e:
                print(f"Error on interchange page: {str(e)}")
        
        # Save screenshot of final results
        save_debug_info("final_results", always_save=True)
        
        # Verify results contain expected information
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Extract search terms for verification
        search_terms = []
        if year:
            search_terms.append(year)
        if model:
            search_terms.extend([term.lower() for term in model.split() if len(term) > 2])
        if selected_part:
            main_part_terms = [term.lower() for term in selected_part.split() if len(term) > 2 
                              and term.lower() not in ["display", "image", "with", "w"]]
            search_terms.extend(main_part_terms)
        
        print(f"Looking for these search terms on page: {search_terms}")
        
        # Check if terms appear on page
        search_terms_found = []
        for term in search_terms:
            if term.lower() in page_text.lower():
                search_terms_found.append(term)
        
        # Determine test result
        if "No parts found" in page_text or "no parts were found" in page_text.lower():
            print("TEST FAILED: No parts found")
            result = "F - No parts found"
        elif len(search_terms_found) >= len(search_terms) * 0.7:  # Found at least 70% of terms
            print(f"Found search terms on page: {search_terms_found}")
            result = "P - Search terms verified"
            print(f"TEST PASSED: {result}")
        else:
            print(f"Only found these search terms: {search_terms_found}")
            print("TEST FAILED: Could not verify search terms on page")
            result = "F - Could not verify search terms"
            
        return {
            'Search': test_data['Search Year|Make Model|Group|Part'],
            'Expected': test_data['Expected'],
            'Result': result
        }
    except Exception as e:
        raise e  # Let the main error handler deal with it

# Handles searching with a desktop app-specific approach
def app_search(test_data, platform):
    """Perform search using app platform approach with dropdowns"""
    try:
        # Parse test data
        parts = test_data['Search Year|Make Model|Group|Part'].split('|')
        year = parts[0]
        model = parts[1]
        part_group = parts[2] if len(parts) > 2 else ""
        part = parts[3] if len(parts) > 3 else ""
        
        # Take a screenshot of the initial page
        save_debug_info("initial_page", always_save=True)
        
        # ===== 1. Select Year =====
        print(f"Selecting year: {year}")
        try:
            # Try standard select dropdown
            year_select = Select(driver.find_element(By.CSS_SELECTOR, "#year"))
            year_select.select_by_visible_text(year)
            print(f"Selected year using standard dropdown")
        except:
            try:
                # Try to find any year dropdown on the page
                year_elements = driver.find_elements(By.XPATH, "//select[contains(@id, 'year')]")
                if year_elements:
                    print(f"Found {len(year_elements)} year-related dropdowns")
                    for i, elem in enumerate(year_elements):
                        try:
                            year_select = Select(elem)
                            year_select.select_by_visible_text(year)
                            print(f"Selected year using dropdown #{i}")
                            break
                        except:
                            continue
                else:
                    raise Exception("Could not find year dropdown")
            except Exception as e:
                print(f"Error selecting year: {str(e)}")
                raise Exception(f"Could not select year: {str(e)}")
        
        # Wait for make/model dropdown to populate
        time.sleep(WAIT_TIME/2)
        save_debug_info("after_year_selection", always_save=True)
        
        # ===== 2. Select Make/Model =====
        print(f"Selecting model: {model}")
        try:
            # Try standard model dropdown
            model_select = Select(driver.find_element(By.CSS_SELECTOR, "#model"))
            
            # Check for dropdown issues
            dropdown_issues = check_dropdown_issues(model_select)
            if dropdown_issues:
                print("Model Dropdown Issues Found:")
                for issue in dropdown_issues[:5]:  # Show just the first few
                    print(f"  - {issue}")
            
            # Select the model
            try:
                model_select.select_by_visible_text(model)
                print(f"Selected model: {model}")
            except:
                # Try to find a model that contains our model text
                options = [o.text for o in model_select.options]
                found = False
                for option in options:
                    if model.lower() in option.lower():
                        model_select.select_by_visible_text(option)
                        print(f"Selected similar model: {option}")
                        found = True
                        break
                
                if not found:
                    print("Available models:")
                    for option in options:
                        print(f"  - {option}")
                    raise Exception(f"Could not find model '{model}' in dropdown")
                
        except Exception as e:
            print(f"Error selecting model: {str(e)}")
            raise Exception(f"Could not select model: {str(e)}")
        
        # Wait for part dropdown to populate
        time.sleep(WAIT_TIME/2)
        save_debug_info("after_model_selection", always_save=True)
        
        # ===== 3. Select Part =====
        print(f"Selecting part: {part}")
        try:
            # Try to find the part dropdown
            part_selectors = [
                "#part",
                "select[name='part']",
                "select[id*='part']"
            ]
            
            part_select = None
            for selector in part_selectors:
                try:
                    part_select = Select(driver.find_element(By.CSS_SELECTOR, selector))
                    print(f"Found part dropdown using selector: {selector}")
                    break
                except:
                    continue
            
            if not part_select:
                # Try to find any part-related dropdown
                part_elements = driver.find_elements(By.XPATH, "//select[contains(@id, 'part') or contains(@name, 'part')]")
                if part_elements:
                    print(f"Found {len(part_elements)} part-related dropdowns")
                    part_select = Select(part_elements[0])
                    print(f"Using first part dropdown with id: {part_elements[0].get_attribute('id')}")
                else:
                    raise Exception("Could not find part dropdown")
            
            # Check for dropdown issues before making selection
            dropdown_issues = check_dropdown_issues(part_select)
            if dropdown_issues:
                print("Part Dropdown Issues Found:")
                for issue in dropdown_issues[:5]:  # Show just the first few
                    print(f"  - {issue}")
            
            # Get all part options for reference
            all_options = [option.text for option in part_select.options]
            
            # Debug output to see available options
            print(f"Found {len(all_options)} part options. First 10:")
            for i, option in enumerate(all_options[:10]):
                print(f"{i}: {option}")
            
            # Try to select the part
            found = False
            part_mismatch_warning = False
            selected_part = ""
            
            # 1. First try: Exact match for the whole part name
            if not found and part:
                try:
                    exact_matches = [opt for opt in all_options if part.lower() == opt.lower()]
                    if exact_matches:
                        part_select.select_by_visible_text(exact_matches[0])
                        print(f"Selected exact match part: {exact_matches[0]}")
                        selected_part = exact_matches[0]
                        found = True
                except Exception as e:
                    print(f"Error finding exact part match: {str(e)}")
            
            # 2. Second try: Find options containing all words in the part name
            if not found and part:
                try:
                    part_words = [w.lower() for w in part.split() if len(w) > 2 
                                 and w.lower() not in ["display", "image", "with", "w"]]
                    
                    # Find options containing ALL important words
                    for option_text in all_options:
                        option_lower = option_text.lower()
                        if all(word in option_lower for word in part_words):
                            part_select.select_by_visible_text(option_text)
                            print(f"Selected part containing all keywords: {option_text}")
                            selected_part = option_text
                            found = True
                            break
                except Exception as e:
                    print(f"Error finding part with all keywords: {str(e)}")
            
            # 3. Third try: Match any part containing key words
            if not found:
                try:
                    part_words = [w for w in part.lower().split() if len(w) > 2 
                                 and w not in ["display", "image", "with", "w"]]
                    
                    for option_text in all_options:
                        lower_option = option_text.lower()
                        if any(word in lower_option for word in part_words):
                            part_select.select_by_visible_text(option_text)
                            print(f"Selected partial keyword match part: {option_text}")
                            selected_part = option_text
                            found = True
                            
                            # Check if this is potentially a wrong selection
                            if not all(word in lower_option for word in part_words):
                                print(f"⚠️ WARNING: Selected part '{option_text}' may not match requested part '{part}'")
                                part_mismatch_warning = True
                            
                            break
                except Exception as e:
                    print(f"Error finding partial keyword match: {str(e)}")
            
            # Last resort: Select first non-empty option
            if not found:
                try:
                    for option_text in all_options:
                        if option_text and option_text != "Select Part":
                            part_select.select_by_visible_text(option_text)
                            print(f"Selected first available part: {option_text}")
                            selected_part = option_text
                            found = True
                            
                            # This is definitely not what was requested
                            print(f"⚠️ WARNING: Selected part '{option_text}' does not match requested part '{part}'")
                            part_mismatch_warning = True
                            
                            break
                except Exception as e:
                    print(f"Error selecting fallback part: {str(e)}")
            
            if not found:
                raise Exception(f"Could not select any part")
            
        except Exception as e:
            print(f"Error selecting part: {str(e)}")
            raise Exception(f"Could not select part: {str(e)}")
        
        save_debug_info("after_part_selection", always_save=True)
        
        # ===== 4. Enter ZIP code if needed =====
        try:
            zip_field = driver.find_element(By.XPATH, 
                "//input[@type='text' and (contains(@placeholder, 'zip') or contains(@name, 'zip') or @maxlength='5')]")
            
            zip_field.clear()
            zip_field.send_keys("41094")
            print("Entered ZIP code: 41094")
        except:
            print("ZIP code field not found, may not be needed")
        
        # ===== 5. Click Search button =====
        print("Clicking search button...")
        search_button_clicked = False
        
        # Try multiple possible search button selectors
        search_button_selectors = [
            "input[type='submit'][value='Search']",
            "button[type='submit']",
            "input[type='image'][alt='Search']",
            "input.searchButton",
            "#search_button"
        ]
        
        for selector in search_button_selectors:
            try:
                search_buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for button in search_buttons:
                    if button.is_displayed():
                        if try_click(button, f"search button ({selector})"):
                            search_button_clicked = True
                            break
                if search_button_clicked:
                    break
            except:
                continue
        
        if not search_button_clicked:
            # Try to find any clickable button/input with search-related attributes
            try:
                search_elements = driver.find_elements(By.XPATH, 
                    "//input[@type='submit' or @type='image' or @type='button'] | //button")
                
                for element in search_elements:
                    try:
                        if element.is_displayed():
                            element_text = element.text.lower() if element.text else ""
                            element_value = element.get_attribute("value")
                            element_value = element_value.lower() if element_value else ""
                            
                            # Check if this looks like a search button
                            if ("search" in element_text or "search" in element_value or
                                "go" in element_text or "find" in element_text):
                                
                                if try_click(element, "detected search button"):
                                    search_button_clicked = True
                                    break
                    except:
                        continue
            except:
                pass
        
        if not search_button_clicked:
            # Last resort - try submitting the form
            try:
                forms = driver.find_elements(By.TAG_NAME, "form")
                if forms:
                    forms[0].submit()
                    print("Submitted form")
                    search_button_clicked = True
            except Exception as e:
                print(f"Could not submit form: {str(e)}")
                raise Exception("Could not find search button or submit form")
        
        # Wait for results page to load
        time.sleep(WAIT_TIME * 2)
        save_debug_info("results_page", always_save=True)
        
        # Get page title and URL for context
        current_url = driver.current_url
        page_title = driver.title
        print(f"Current page: {page_title} - {current_url}")
        
        # Extract some of the page text for analysis
        page_text = driver.find_element(By.TAG_NAME, "body").text
        print(f"Page text preview: {page_text[:200]}...")
        
        # Look for search verification - more flexible approach
        search_verification = False
        
        # Extract key terms from our search
        search_terms = []
        if year:
            search_terms.append(year)
        if model:
            # Handle multi-word models by splitting
            search_terms.extend([term.lower() for term in model.split() if len(term) > 2])
        if selected_part:
            # Get the main part name without parentheses
            main_part = selected_part.split('(')[0].strip().lower()
            if main_part:
                search_terms.append(main_part)
        
        print(f"Looking for these search terms on page: {search_terms}")
        
        # Check if all search terms appear on the page
        search_terms_found = []
        for term in search_terms:
            if term.lower() in page_text.lower():
                search_terms_found.append(term)
        
        # If we found most of the important terms, consider it a match
        if len(search_terms_found) >= len(search_terms) * 0.7:  # Found at least 70% of terms
            search_verification = True
            print(f"Found search terms on page: {search_terms_found}")
        else:
            print(f"Only found these search terms: {search_terms_found}")
        
        # Determine test result
        if "No parts found" in page_text or "no parts were found" in page_text.lower():
            print("TEST FAILED: No parts found")
            result = "F - No parts found"
        elif search_verification:
            if part_mismatch_warning:
                result = f"P* - Search terms verified but selected '{selected_part}' instead of '{part}'"
            else:
                result = "P - Search terms verified"
                
            if dropdown_issues:
                # Add a note about dropdown issues
                issue_count = len(dropdown_issues)
                result += f" (Note: {issue_count} dropdown issues found)"
                
            print(f"TEST PASSED: {result}")
        else:
            print("TEST FAILED: Could not verify search terms on page")
            result = "F - Could not verify search terms"
            
        return {
            'Search': test_data['Search Year|Make Model|Group|Part'],
            'Expected': test_data['Expected'],
            'Result': result
        }
    except Exception as e:
        raise e

# Handles searching for the Pro platform with login
def pro_search(test_data, platform):
    """Perform search using pro platform approach with login first"""
    try:
        # Parse test data
        parts = test_data['Search Year|Make Model|Group|Part'].split('|')
        year = parts[0]
        model = parts[1]
        part = parts[3] if len(parts) > 3 else ""
        
        # Check for special 'ABSENT' expected result
        expected_result = "PRESENT"  # Default
        if 'ExpectedResult' in test_data:
            expected_result = test_data['ExpectedResult']
        
        # Take a screenshot of the initial page after login
        save_debug_info("initial_pro_page", always_save=True)
        
        # Check if we need to click on the dropdown link first (Car-Part Pro site specific)
        try:
            dropdown_link = driver.find_element(By.CSS_SELECTOR, "#vin_dropdown_link")
            if dropdown_link.is_displayed():
                print("Found dropdown link, clicking to enable dropdown search...")
                try_click(dropdown_link, "dropdown link")
                time.sleep(WAIT_TIME)  # Wait for dropdowns to appear
                
                # Save a screenshot after clicking the dropdown link
                save_debug_info("after_dropdown_link", always_save=True)
        except:
            print("No dropdown link found, continuing with standard search")
        
        # Select Year
        print(f"Selecting year: {year}")
        try:
            # Try Car-Part Pro specific year selector
            year_select = Select(driver.find_element(By.CSS_SELECTOR, "#year_dropdown"))
            year_select.select_by_visible_text(year)
            print(f"Selected year using #year_dropdown")
        except:
            try:
                # Try standard selector
                year_select = Select(driver.find_element(By.CSS_SELECTOR, "#year"))
                year_select.select_by_visible_text(year)
                print(f"Selected year using #year")
            except Exception as e:
                print(f"Error selecting year: {str(e)}")
                raise Exception(f"Could not select year: {str(e)}")
        
        # Wait for make/model dropdown to populate
        time.sleep(WAIT_TIME/2)
        
        # Select Model
        print(f"Selecting model: {model}")
        try:
            # Try Car-Part Pro specific model selector
            model_select = Select(driver.find_element(By.CSS_SELECTOR, "#model_dropdown"))
            model_select.select_by_visible_text(model)
            print(f"Selected model using #model_dropdown")
        except:
            try:
                # Try standard selector
                model_select = Select(driver.find_element(By.CSS_SELECTOR, "#model"))
                model_select.select_by_visible_text(model)
                print(f"Selected model using #model")
            except Exception as e:
                print(f"Error selecting model: {str(e)}")
                
                # Try to find a close match in the dropdown
                try:
                    model_elements = driver.find_elements(By.XPATH, "//select[contains(@id, 'model')]")
                    if model_elements:
                        # Try to find a similar model in any dropdown
                        model_lower = model.lower()
                        for elem in model_elements:
                            try:
                                model_select = Select(elem)
                                options = [option.text for option in model_select.options]
                                
                                # Try to find a similar model
                                for option in options:
                                    if model_lower in option.lower():
                                        model_select.select_by_visible_text(option)
                                        print(f"Selected similar model: {option}")
                                        # Update model for verification
                                        model = option
                                        break
                            except:
                                continue
                except Exception as e2:
                    print(f"Could not find similar model: {str(e2)}")
                    raise Exception(f"Could not select model: {str(e)}")
        
        # Wait for part dropdown to populate
        time.sleep(WAIT_TIME/2)
        save_debug_info("after_model_selection", always_save=True)
        
        # After selecting year and model, click the part dropdown link if it exists
        try:
            part_dropdown_link = driver.find_element(By.CSS_SELECTOR, "#part_dropdown_link")
            if part_dropdown_link.is_displayed():
                print("Found part dropdown link, clicking to enable part selection...")
                try_click(part_dropdown_link, "part dropdown link")
                time.sleep(WAIT_TIME)  # Wait for part dropdown to appear
                
                # Save a screenshot after clicking the part dropdown link
                save_debug_info("after_part_dropdown_link", always_save=True)
        except:
            print("No part dropdown link found, continuing with standard part selection")
        
        # Select Part
        print(f"Selecting part: {part}")
        try:
            # First try Car-Part Pro specific part selectors
            part_selectors = [
                "#part_dropdown",  # Try specific Car-Part Pro selector first
                "select[name='part']",
                "select[id*='part']"
            ]
            
            found_part_select = False
            for selector in part_selectors:
                try:
                    part_select = Select(driver.find_element(By.CSS_SELECTOR, selector))
                    print(f"Found part dropdown using selector: {selector}")
                    found_part_select = True
                    break
                except:
                    continue
            
            if not found_part_select:
                # Try to find any part-related dropdown
                part_elements = driver.find_elements(By.XPATH, "//select[contains(@id, 'part') or contains(@name, 'part')]")
                if part_elements:
                    print(f"Found {len(part_elements)} part-related dropdowns")
                    part_select = Select(part_elements[0])
                    print(f"Using first part dropdown with id: {part_elements[0].get_attribute('id')}")
                else:
                    raise Exception("Could not find part dropdown")
                
        except Exception as e:
            print(f"Error finding part dropdown: {str(e)}")
            save_debug_info("part_dropdown_error", always_save=True)
            raise Exception(f"Could not find part dropdown: {str(e)}")
        
        # Check if we expect the part to be ABSENT
        if expected_result == "ABSENT":
            part_options = [option.text for option in part_select.options]
            if part not in part_options:
                print(f"✓ SUCCESS: Part '{part}' correctly absent from dropdown")
                return {
                    'Search': test_data['Search Year|Make Model|Group|Part'],
                    'Expected': test_data['Expected'],
                    'Result': f"P - Part correctly absent from dropdown"
                }
            else:
                print(f"✗ ERROR: Part '{part}' found in dropdown but expected to be absent")
                return {
                    'Search': test_data['Search Year|Make Model|Group|Part'],
                    'Expected': test_data['Expected'],
                    'Result': f"F - Part incorrectly present in dropdown"
                }
        
        # Check for dropdown issues before making selection
        dropdown_issues = check_dropdown_issues(part_select)
        if dropdown_issues:
            print("Dropdown Issues Found:")
            for issue in dropdown_issues[:5]:  # Show just the first few
                print(f"  - {issue}")
        
        # Get all part options for reference
        all_options = [option.text for option in part_select.options]
        
        # Debug output to see available options
        print(f"Found {len(all_options)} part options. First 10:")
        for i, option in enumerate(all_options[:10]):
            print(f"{i}: {option}")
        
        # Improved part selection logic
        found = False
        part_mismatch_warning = False
        selected_part = ""
        
        # 1. First try: Exact match for the whole part name
        if not found and part:
            try:
                exact_matches = [opt for opt in all_options if part.lower() == opt.lower()]
                if exact_matches:
                    part_select.select_by_visible_text(exact_matches[0])
                    print(f"Selected exact match part: {exact_matches[0]}")
                    selected_part = exact_matches[0]
                    found = True
            except Exception as e:
                print(f"Error finding exact part match: {str(e)}")
        
        # 2. Second try: Find options containing all words in the part name
        if not found and part:
            try:
                part_words = [w.lower() for w in part.split() if len(w) > 2 
                             and w.lower() not in ["display", "image", "with", "w"]]
                
                # Find options containing ALL important words
                for option_text in all_options:
                    option_lower = option_text.lower()
                    if all(word in option_lower for word in part_words):
                        part_select.select_by_visible_text(option_text)
                        print(f"Selected part containing all keywords: {option_text}")
                        selected_part = option_text
                        found = True
                        break
            except Exception as e:
                print(f"Error finding part with all keywords: {str(e)}")
        
        # 3. Third try: Match display w image or display w/o image variants
        if not found and "display" in part.lower() and "image" in part.lower():
            try:
                # Try to match "display w image" or similar variants
                part_words = [w for w in part.lower().split() if w not in ["display", "w", "image", "with"]]
                
                for option_text in all_options:
                    lower_option = option_text.lower()
                    if ("display" in lower_option and "image" in lower_option):
                        # Check if the main part words match (e.g., "wheel", "hub cap")
                        if any(word in lower_option for word in part_words if len(word) > 2):
                            part_select.select_by_visible_text(option_text)
                            print(f"Selected display/image variant part: {option_text}")
                            selected_part = option_text
                            found = True
                            break
            except Exception as e:
                print(f"Error finding display/image variant: {str(e)}")
        
        # 4. Fourth try: Match any part containing key words
        if not found:
            try:
                part_words = [w for w in part.lower().split() if len(w) > 2 
                             and w not in ["display", "image", "with", "w"]]
                
                for option_text in all_options:
                    lower_option = option_text.lower()
                    if any(word in lower_option for word in part_words):
                        part_select.select_by_visible_text(option_text)
                        print(f"Selected partial keyword match part: {option_text}")
                        selected_part = option_text
                        found = True
                        
                        # Check if this is potentially a wrong selection
                        if not all(word in lower_option for word in part_words):
                            print(f"⚠️ WARNING: Selected part '{option_text}' may not match requested part '{part}'")
                            part_mismatch_warning = True
                        
                        break
            except Exception as e:
                print(f"Error finding partial keyword match: {str(e)}")
        
        # Last resort: Select first non-empty option
        if not found:
            try:
                for option_text in all_options:
                    if option_text and option_text != "Select Part":
                        part_select.select_by_visible_text(option_text)
                        print(f"Selected first available part: {option_text}")
                        selected_part = option_text
                        found = True
                        
                        # This is definitely not what was requested
                        print(f"⚠️ WARNING: Selected part '{option_text}' does not match requested part '{part}'")
                        part_mismatch_warning = True
                        
                        break
            except Exception as e:
                print(f"Error selecting fallback part: {str(e)}")
        
        if not found:
            raise Exception("Could not select any part")
        
        # Click Search Button
        print("Clicking search button...")
        search_button_found = False
        
        # Try multiple possible search button selectors
        search_button_selectors = [
            "body > div.wrapper > div.search > div > table > tbody > tr:nth-child(2) > td > div > div > a > img",  # Car-Part Pro specific
            "input[type='submit'][value='Search']",
            "button[type='submit']",
            "input[type='image'][alt='Search']",
            "input.searchButton",
            "#search_button"
        ]
        
        for selector in search_button_selectors:
            try:
                search_buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                if search_buttons:
                    for button in search_buttons:
                        if button.is_displayed():
                            if try_click(button, f"search button ({selector})"):
                                search_button_found = True
                                break
                    if search_button_found:
                        break
            except:
                continue
        
        if not search_button_found:
            # Try to find any clickable button/input with search-related attributes
            try:
                search_elements = driver.find_elements(By.XPATH, 
                    "//input[@type='submit' or @type='image' or @type='button'] | //button")
                
                for element in search_elements:
                    try:
                        if element.is_displayed():
                            element_text = element.text.lower() if element.text else ""
                            element_value = element.get_attribute("value")
                            element_value = element_value.lower() if element_value else ""
                            element_id = element.get_attribute("id")
                            element_id = element_id.lower() if element_id else ""
                            
                            # Check if this looks like a search button
                            if ("search" in element_text or 
                                "search" in element_value or 
                                "search" in element_id or
                                "go" in element_text or 
                                "find" in element_text):
                                
                                if try_click(element, "detected search button"):
                                    search_button_found = True
                                    break
                    except:
                        continue
            except:
                pass
        
        if not search_button_found:
            # Last resort - try pressing Enter on the last input field
            try:
                active_element = driver.switch_to.active_element
                active_element.send_keys(Keys.RETURN)
                print("Pressed Enter to submit search")
                search_button_found = True
            except:
                save_debug_info("search_button_not_found", always_save=True)
                raise Exception("Could not find search button")
        
        # Wait for results page to load
        print("Waiting for results page...")
        time.sleep(WAIT_TIME * 2)
        
        # Save debug information
        save_debug_info(f"results_page")
        
        # Get page title and URL for context
        current_url = driver.current_url
        page_title = driver.title
        print(f"Current page: {page_title} - {current_url}")
        
        # Get page text for analysis
        page_text = driver.find_element(By.TAG_NAME, "body").text
        print(f"Page text preview: {page_text[:200]}...")
        
        # Look for search verification - more flexible approach
        search_verification = False
        
        # Extract key terms from our search
        search_terms = []
        if year:
            search_terms.append(year)
        if model:
            # Handle multi-word models by splitting
            search_terms.extend([term.lower() for term in model.split() if len(term) > 2])
        if selected_part:
            # Get the main part name without parentheses
            main_part = selected_part.split('(')[0].strip().lower()
            if main_part:
                search_terms.append(main_part)
        
        print(f"Looking for these search terms on page: {search_terms}")
        
        # Check if all search terms appear on the page
        search_terms_found = []
        for term in search_terms:
            if term.lower() in page_text.lower():
                search_terms_found.append(term)
        
        # If we found most of the important terms, consider it a match
        if len(search_terms_found) >= len(search_terms) * 0.7:  # Found at least 70% of terms
            search_verification = True
            print(f"Found search terms on page: {search_terms_found}")
        else:
            print(f"Only found these search terms: {search_terms_found}")
        
        # Determine test result
        if "No parts found" in page_text or "no parts were found" in page_text.lower():
            print("TEST FAILED: No parts found")
            result = "F - No parts found"
        elif search_verification:
            if part_mismatch_warning:
                result = f"P* - Part details verified but selected '{selected_part}' instead of '{part}'"
            else:
                result = "P - Part details verified"
            # Add a concise summary of dropdown issues if any
            if dropdown_issues:
                issue_count = len(dropdown_issues)
                duplicate_count = sum(1 for issue in dropdown_issues if "Duplicate dropdown option" in issue)
                order_count = sum(1 for issue in dropdown_issues if "out of order" in issue)
                result += f" ({duplicate_count} duplicates, {order_count} ordering issues)"
                
            print(f"TEST PASSED: {result}")
        else:
            print("TEST FAILED: Could not verify search terms on page")
            result = "F - Could not verify search terms"
        
        return {
            'Search': test_data['Search Year|Make Model|Group|Part'],
            'Expected': test_data['Expected'],
            'Result': result
        }
    except Exception as e:
        raise e

# Main test runner function
def run_tests():
    try:
        # Load all test cases
        test_cases = pd.read_csv(args.test_set)
        print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
        
        results = []
        all_dropdown_issues = []  # Track dropdown issues for reporting
        
        # Get platform configuration
        platform = config["platforms"][0]
        
        # Navigate to the configured URL
        driver.get(platform["url"])
        print(f"Opened website: {platform['url']}")
        
        # Handle login if required
        if not handle_login(platform):
            raise Exception(f"Failed to log in to {platform['name']}")
        
        # Wait for the page to load
        time.sleep(WAIT_TIME)
        
        # Process each test case
        for index, test_data in test_cases.iterrows():
            print(f"\n{'='*80}\nTesting case {index+1}/{len(test_cases)}: {test_data['Search Year|Make Model|Group|Part']}\n{'='*80}")
            
            try:
                # Use the appropriate search method based on platform type
                if PLATFORM == "web":
                    result = web_search(test_data, platform)
                elif PLATFORM == "app":
                    result = app_search(test_data, platform)
                elif PLATFORM == "pro":
                    result = pro_search(test_data, platform)
                else:
                    raise Exception(f"Unsupported platform type: {PLATFORM}")
                
                # Store the result
                results.append(result)
                
                # Reset for next test
                try:
                    # Navigate back to main search page
                    driver.get(platform["url"])
                    print("Navigated back to start for next test")
                    time.sleep(WAIT_TIME * 2)
                    
                    # Re-login if needed (session may have expired)
                    if platform.get("requires_login", False):
                        handle_login(platform)
                        
                except Exception as e:
                    print(f"Error resetting for next test: {str(e)}")
                    
            except Exception as e:
                # Enhanced error handling
                result = handle_test_error(e, test_data, index)
                results.append(result)
                
                # Even after error, try to reset to search screen for next test
                try:
                    driver.get(platform["url"])
                    time.sleep(WAIT_TIME * 2)
                    
                    # Re-login if needed
                    if platform.get("requires_login", False):
                        handle_login(platform)
                except:
                    print("Could not reset to search page after error")
                    
                continue  # Continue to next test case
        
        # Save final results to CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_df = pd.DataFrame(results)
        results_file = f"results_{timestamp}.csv"
        results_df.to_csv(results_file, index=False)
        print(f"\nTesting complete! Results saved to {results_file}")
        
        # Save detailed dropdown issues log if issues were found
        if all_dropdown_issues:
            issues_log_file = f"dropdown_issues_{timestamp}.txt"
            with open(issues_log_file, 'w') as f:
                for i, (test_case, issues) in enumerate(all_dropdown_issues):
                    f.write(f"Dropdown issues for test case {i+1}: {test_case}\n")
                    f.write("-" * 80 + "\n")
                    for issue in issues:
                        f.write(f"  - {issue}\n")
                    f.write("\n\n")
            print(f"Detailed dropdown issues log saved to {issues_log_file}")
        
        # Summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r['Result'].startswith('P'))
        failed_tests = total_tests - passed_tests
        warning_tests = sum(1 for r in results if r['Result'].startswith('P*'))
        
        print(f"\nTest Summary:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed Tests: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        if warning_tests > 0:
            print(f"  Passed with Warnings: {warning_tests} ({warning_tests/total_tests*100:.1f}%)")
        print(f"  Failed Tests: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        # Keep browser open for inspection if not in headless mode
        if not args.headless:
            input("Press Enter to close the browser...")
        
    except Exception as e:
        print(f"FATAL ERROR: {str(e)}")
        # Save screenshot when an error occurs
        debug_file = save_debug_info("fatal_error", error_occurred=True)
        print(f"Saved error debug info to {debug_file}")
        
    finally:
        print("Test complete")
        if args.headless:
            driver.quit()

if __name__ == "__main__":
    run_tests()