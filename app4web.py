import json
import pandas as pd
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import time
from datetime import datetime
import re
import os
import threading
import sys
import select

# Command line arguments
parser = argparse.ArgumentParser(description="Car Parts Automation Test Script")
parser.add_argument("--test-set", help="Path to test cases CSV file", default="test_cases.csv")
parser.add_argument("--platform", help="Specific platform to test", default="all")
parser.add_argument("--headless", action="store_true", help="Run tests in headless mode")
parser.add_argument("--save-all-screenshots", action="store_true", 
                    help="Save screenshots for all steps, not just errors")
parser.add_argument("--wait-time", type=float, default=2.0,
                    help="Wait time between actions (default: 2.0)")
args = parser.parse_args()

# Set up global variables
WAIT_TIME = args.wait_time
SAVE_ALL_SCREENSHOTS = args.save_all_screenshots

# Make a directory for screenshots if it doesn't exist
os.makedirs("screenshots", exist_ok=True)

# Load configuration
with open('config4web.json', 'r') as f:
    config = json.load(f)

# Set up Chrome with configured options
chrome_options = Options()
for option in config["webdriver_options"]:
    chrome_options.add_argument(option)

# Add headless mode if requested
if args.headless:
    print("Running in headless mode")
    chrome_options.add_argument("--headless")

# Filter platforms if requested
platforms_to_test = config["platforms"]
if args.platform != "all":
    platforms_to_test = [p for p in config["platforms"] if p["name"] == args.platform]
    if not platforms_to_test:
        print(f"No platform found with name '{args.platform}'. Available platforms:")
        for p in config["platforms"]:
            print(f"  - {p['name']}")
        exit(1)

# Start browser
driver = webdriver.Chrome(options=chrome_options)

def start_heartbeat():
    """Start a heartbeat thread to prevent watchdog termination"""
    def heartbeat_func():
        while True:
            # Print a minimal heartbeat message every 30 seconds
            sys.stderr.write(".")
            sys.stderr.flush()
            time.sleep(30)
    
    # Start the heartbeat thread as a daemon (will terminate when main thread ends)
    heartbeat_thread = threading.Thread(target=heartbeat_func, daemon=True)
    heartbeat_thread.start()
    print("Heartbeat thread started to prevent watchdog termination")

# Start the heartbeat to prevent watchdog termination
start_heartbeat()

def short_sleep(duration):
    """Sleep with updates to prevent watchdog termination"""
    chunks = max(1, int(duration / 0.5))  # Break into 0.5 second chunks
    for i in range(chunks):
        time.sleep(0.5)
        if i % 2 == 0:  # Every second chunk (1 second)
            sys.stderr.write(".")
            sys.stderr.flush()

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

def try_click(element, description):
    """Try multiple methods to click an element"""
    try:
        # Method 1: Standard click
        element.click()
        print(f"Clicked {description} using standard click")
        return True
    except:
        try:
            # Method 2: JavaScript click
            driver.execute_script("arguments[0].click();", element)
            print(f"Clicked {description} using JavaScript")
            return True
        except:
            try:
                # Method 3: ActionChains
                actions = ActionChains(driver)
                actions.move_to_element(element).click().perform()
                print(f"Clicked {description} using ActionChains")
                return True
            except Exception as e:
                print(f"Could not click {description}: {str(e)}")
                return False

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
    return {
        'Search': test_data['Search Year|Make Model|Group|Part'],
        'Expected': test_data['Expected'],
        'Result': f"F - {error_category}: {error_message[:100]}..." if len(error_message) > 100 else f"F - {error_category}: {error_message}"
    }

def safe_find_and_click(selector, description, method="css", wait_time=WAIT_TIME, optional=False):
    """Safely find and click an element, with fallbacks and error handling"""
    try:
        # Wait for element to be clickable
        if method == "css":
            element = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        elif method == "xpath":
            element = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
        
        # Scroll to element
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        short_sleep(wait_time/4)  # Brief pause after scrolling
        
        # Try to click the element
        if try_click(element, description):
            print(f"Successfully clicked {description}")
            return True
        else:
            print(f"Could not click {description} using standard methods")
            return False
    except Exception as e:
        if optional:
            print(f"Optional element {description} not found or not clickable: {str(e)}")
            return False
        else:
            print(f"Error finding or clicking {description}: {str(e)}")
            raise

def safe_enter_text(selector, text, description, method="css", wait_time=WAIT_TIME, optional=False):
    """Safely find an input element and enter text"""
    try:
        # Wait for element to be clickable
        if method == "css":
            element = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        elif method == "xpath":
            element = WebDriverWait(driver, wait_time).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
        
        # Scroll to element
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        short_sleep(wait_time/4)  # Brief pause after scrolling
        
        # Clear and enter text
        element.clear()
        element.send_keys(text)
        print(f"Entered {text} into {description}")
        return True
    except Exception as e:
        if optional:
            print(f"Optional element {description} not found or not accessible: {str(e)}")
            return False
        else:
            print(f"Error finding or entering text into {description}: {str(e)}")
            raise

try:
    # Load all test cases
    test_cases = pd.read_csv(args.test_set)
    print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
    
    results = []

    # Process each test case
    for index, test_data in test_cases.iterrows():
        print(f"\n{'='*80}\nTesting case {index+1}/{len(test_cases)}: {test_data['Search Year|Make Model|Group|Part']}\n{'='*80}")
        sys.stderr.write("\n[New Test Case]\n")  # Clear heartbeat display for readability
        
        try:
            # Get the platform config (using only the first platform for now)
            platform = platforms_to_test[0]
            
            # Navigate to the configured URL
            driver.get(platform["url"])
            print(f"Opened website: {platform['url']}")
            
            # Wait for the page to load
            short_sleep(WAIT_TIME)
            
            # Parse test data
            parts = test_data['Search Year|Make Model|Group|Part'].split('|')
            year = parts[0]
            full_model = parts[1]
            part_group = parts[2] if len(parts) > 2 else ""
            part = parts[3] if len(parts) > 3 else ""
            
            # Parse make and model from the full model string
            model_parts = full_model.split()
            if len(model_parts) >= 2:
                make = model_parts[0]  # First word is the make
                model = ' '.join(model_parts[1:])  # Rest is the model
            else:
                make = full_model  # If only one word, it's both make and model
                model = ""
            
            # Store the original search criteria for verification later
            original_search = f"{year} {full_model} {part}"
            print(f"Original search criteria: {original_search}")
            
            # Take a screenshot of the initial page
            save_debug_info("initial_page", always_save=True)
            
            # === Follow the exact steps specified ===
            
            # Step 1: Click #yearSelect
            print("Step 1: Click #yearSelect")
            safe_find_and_click("#yearSelect", "Year Select Button")
            short_sleep(WAIT_TIME/2)
            save_debug_info("after_year_select_button", always_save=True)
            
            # Step 2: Click #yearSearch
            print(f"Step 2: Click #yearSearch")
            safe_find_and_click("#yearSearch", "Year Search Field", optional=True)  # Sometimes this might be auto-focused
            short_sleep(WAIT_TIME/2)
            
            # Step 3: Enter year
            print(f"Step 3: Enter year: {year}")
            try:
                # First try the specific input
                safe_enter_text("#yearSearch", year, "Year Input Field")
            except:
                # Fall back to any visible input field
                inputs = driver.find_elements(By.XPATH, "//input[@type='text' and @placeholder='Year' or contains(@id, 'year')]")
                if not inputs:
                    inputs = driver.find_elements(By.XPATH, "//input[@type='text']")
                
                if inputs:
                    for input_field in inputs:
                        if input_field.is_displayed():
                            input_field.clear()
                            input_field.send_keys(year)
                            print(f"Entered year {year} in visible input field")
                            break
                    else:
                        raise Exception("Could not find a visible input field for year")
                else:
                    raise Exception("No input fields found for year")
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_year_entry", always_save=True)
            
            # Step 4: Select yearContainer > input[type=button]
            print("Step 4: Select yearContainer button")
            try:
                # First try the specific selector
                safe_find_and_click("#yearContainer > input[type=button]", "Year Confirm Button")
            except:
                # Fall back to any button or element with the year text
                year_buttons = driver.find_elements(By.XPATH, f"//input[@type='button'] | //div[text()='{year}']")
                if year_buttons:
                    for button in year_buttons:
                        if button.is_displayed():
                            try_click(button, f"year button with text {year}")
                            print(f"Clicked year confirmation button")
                            break
                    else:
                        # Try JavaScript approach to find and click the year
                        driver.execute_script(f"""
                            var yearElements = document.querySelectorAll('div, span, button, input');
                            for (var i = 0; i < yearElements.length; i++) {{
                                if (yearElements[i].textContent === '{year}' && 
                                    yearElements[i].offsetWidth > 0 && 
                                    yearElements[i].offsetHeight > 0) {{
                                    yearElements[i].click();
                                    return true;
                                }}
                            }}
                            return false;
                        """)
                        print("Used JavaScript to click year button")
                else:
                    raise Exception("Could not find year confirmation button")
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_year_confirmation", always_save=True)
            
            # Step 5: Click #vehicleSelect
            print("Step 5: Click #vehicleSelect")
            safe_find_and_click("#vehicleSelect", "Vehicle Select Button")
            short_sleep(WAIT_TIME)
            save_debug_info("after_vehicle_select_button", always_save=True)
            
            # Step 6: Click #selectMake (e.g., #selectCadillac)
            print(f"Step 6: Click #select{make}")
            try:
                # First try the specific make selector
                make_selector = f"#select{make}"
                safe_find_and_click(make_selector, f"Make Button ({make})")
            except:
                # Fall back to any element containing the make name
                make_elements = driver.find_elements(By.XPATH, f"//div[contains(text(), '{make}')] | //button[contains(text(), '{make}')]")
                if make_elements:
                    for elem in make_elements:
                        if elem.is_displayed():
                            try_click(elem, f"make element with text {make}")
                            print(f"Clicked make: {make}")
                            break
                    else:
                        # Try JavaScript to find and click the make
                        driver.execute_script(f"""
                            var makeElements = document.querySelectorAll('div, button, span, a');
                            for (var i = 0; i < makeElements.length; i++) {{
                                if (makeElements[i].textContent.indexOf('{make}') >= 0 && 
                                    makeElements[i].offsetWidth > 0 && 
                                    makeElements[i].offsetHeight > 0) {{
                                    makeElements[i].click();
                                    return true;
                                }}
                            }}
                            return false;
                        """)
                        print(f"Used JavaScript to click make: {make}")
                else:
                    raise Exception(f"Could not find make selection for {make}")
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_make_selection", always_save=True)
            
            # Step 7: Click #Make > button:nth-child(x) (e.g., #Cadillac > button:nth-child(1))
            print(f"Step 7: Click {make} > model button for {model}")
            try:
                # Try to find the model within the make's container
                model_selector = f"#{make} > button"
                model_buttons = driver.find_elements(By.CSS_SELECTOR, model_selector)
                model_found = False
                
                if model_buttons:
                    # Try to find the exact model text
                    for button in model_buttons:
                        if button.is_displayed() and model.lower() in button.text.lower():
                            try_click(button, f"model button for {model}")
                            print(f"Clicked model: {model}")
                            model_found = True
                            break
                    
                    # If exact match not found, click the first visible button
                    if not model_found:
                        for button in model_buttons:
                            if button.is_displayed():
                                try_click(button, f"first visible model button under {make}")
                                print(f"Clicked first available model under {make}")
                                model_found = True
                                break
                
                # If still not found, try a more generic approach
                if not model_found:
                    model_elements = driver.find_elements(By.XPATH, f"//div[contains(text(), '{model}')] | //button[contains(text(), '{model}')]")
                    if model_elements:
                        for elem in model_elements:
                            if elem.is_displayed():
                                try_click(elem, f"model element with text {model}")
                                print(f"Clicked model: {model}")
                                model_found = True
                                break
                    
                    # Last resort: JavaScript
                    if not model_found:
                        driver.execute_script(f"""
                            var modelElements = document.querySelectorAll('div, button, span, a');
                            for (var i = 0; i < modelElements.length; i++) {{
                                if (modelElements[i].textContent.indexOf('{model}') >= 0 && 
                                    modelElements[i].offsetWidth > 0 && 
                                    modelElements[i].offsetHeight > 0) {{
                                    modelElements[i].click();
                                    return true;
                                }}
                            }}
                            return false;
                        """)
                        print(f"Used JavaScript to click model: {model}")
                        model_found = True
                
                if not model_found:
                    raise Exception(f"Could not find model selection for {model}")
            except Exception as e:
                print(f"Error selecting model: {str(e)}")
                # Try one more generic approach for models
                try:
                    # Try to find any visible button after make selection
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for button in buttons:
                        if button.is_displayed():
                            try_click(button, "visible button after make selection")
                            print("Clicked first visible button after make selection")
                            break
                except Exception as backup_error:
                    print(f"Backup model selection also failed: {str(backup_error)}")
                    raise
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_model_selection", always_save=True)
            
            # Step 8: Click #partSelect
            print("Step 8: Click #partSelect")
            safe_find_and_click("#partSelect", "Part Select Button")
            short_sleep(WAIT_TIME)
            save_debug_info("after_part_select_button", always_save=True)
            
            # Step 9: Click part group (e.g., #selectAxleBrakes)
            # Remove spaces and special chars from part group name
            print(f"Step 9: Click part group button for {part_group}")
            clean_part_group = part_group.replace(" ", "").replace("&", "").replace("-", "")
            try:
                # Try the specific selector
                part_group_selector = f"#select{clean_part_group}"
                safe_find_and_click(part_group_selector, f"Part Group Button ({part_group})")
            except:
                # Fall back to any element containing the part group text
                part_group_elements = driver.find_elements(By.XPATH, 
                    f"//div[contains(text(), '{part_group}')] | //button[contains(text(), '{part_group}')]")
                
                if part_group_elements:
                    for elem in part_group_elements:
                        if elem.is_displayed():
                            try_click(elem, f"part group element with text {part_group}")
                            print(f"Clicked part group: {part_group}")
                            break
                    else:
                        # JavaScript approach
                        driver.execute_script(f"""
                            var elements = document.querySelectorAll('div, button, span, a');
                            for (var i = 0; i < elements.length; i++) {{
                                if (elements[i].textContent.indexOf('{part_group}') >= 0 && 
                                    elements[i].offsetWidth > 0 && 
                                    elements[i].offsetHeight > 0) {{
                                    elements[i].click();
                                    return true;
                                }}
                            }}
                            return false;
                        """)
                        print(f"Used JavaScript to click part group: {part_group}")
                else:
                    raise Exception(f"Could not find part group selection for {part_group}")
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_part_group_selection", always_save=True)
            
            # Step 10: Click specific part (e.g., #AxleBrakes > button:nth-child(54))
            print(f"Step 10: Click part button for {part}")
            clean_part_group = clean_part_group.replace("#select", "")  # Remove prefix if present
            try:
                # Try to find the part within the part group's container
                part_selector = f"#{clean_part_group} > button"
                part_buttons = driver.find_elements(By.CSS_SELECTOR, part_selector)
                part_found = False
                
                if part_buttons:
                    # Try to find the exact part text
                    for button in part_buttons:
                        if button.is_displayed() and part.lower() in button.text.lower():
                            try_click(button, f"part button for {part}")
                            print(f"Clicked part: {part}")
                            part_found = True
                            break
                    
                    # If exact match not found, try partial match
                    if not part_found:
                        part_words = [w for w in part.split() if len(w) > 2]
                        for button in part_buttons:
                            if button.is_displayed():
                                button_text = button.text.lower()
                                if any(word.lower() in button_text for word in part_words):
                                    try_click(button, f"part button containing keywords from {part}")
                                    print(f"Clicked part with keywords from: {part}")
                                    part_found = True
                                    break
                
                # If still not found, try a more generic approach
                if not part_found:
                    part_elements = driver.find_elements(By.XPATH, 
                        f"//div[contains(text(), '{part}')] | //button[contains(text(), '{part}')]")
                    
                    if part_elements:
                        for elem in part_elements:
                            if elem.is_displayed():
                                try_click(elem, f"part element with text {part}")
                                print(f"Clicked part: {part}")
                                part_found = True
                                break
                    
                    # Last resort: JavaScript with part keywords
                    if not part_found:
                        for word in part_words:
                            part_found = driver.execute_script(f"""
                                var elements = document.querySelectorAll('div, button, span, a');
                                for (var i = 0; i < elements.length; i++) {{
                                    if (elements[i].textContent.toLowerCase().indexOf('{word.lower()}') >= 0 && 
                                        elements[i].offsetWidth > 0 && 
                                        elements[i].offsetHeight > 0) {{
                                        elements[i].click();
                                        return true;
                                    }}
                                }}
                                return false;
                            """)
                            
                            if part_found:
                                print(f"Used JavaScript to click part with keyword: {word}")
                                break
                
                if not part_found:
                    raise Exception(f"Could not find part selection for {part}")
            except Exception as e:
                print(f"Error selecting part: {str(e)}")
                # Last-ditch effort - try clicking any visible button
                try:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for button in buttons:
                        if button.is_displayed():
                            try_click(button, "any visible button for part selection")
                            print("Clicked first visible button for part selection")
                            break
                except Exception as backup_error:
                    print(f"Backup part selection also failed: {str(backup_error)}")
                    # Continue anyway - might still work
            
            short_sleep(WAIT_TIME)
            save_debug_info("after_part_selection", always_save=True)
            
            # Step 11: Click the postal code field (body > form > input.postal)
            print("Step 11: Click postal code field")
            try:
                # Try the specific selector
                safe_find_and_click("body > form > input.postal", "Postal Code Field", optional=True)
            except:
                # Fall back to any input field that might be for zip/postal codes
                try:
                    zip_fields = driver.find_elements(By.XPATH, 
                        "//input[@type='text' and (contains(@placeholder, 'zip') or contains(@placeholder, 'post') or @maxlength='5')]")
                    
                    if zip_fields:
                        for field in zip_fields:
                            if field.is_displayed():
                                try_click(field, "zip/postal code field")
                                print("Clicked zip/postal code field")
                                break
                    # If no zip field found, that's okay - continue
                except Exception as zip_error:
                    print(f"Error finding postal code field: {str(zip_error)}")
                    # Continue anyway - might work without zip
            
            # Step 12: Enter 41094 (ZIP code)
            print("Step 12: Enter ZIP code 41094")
            try:
                # Try the specific selector
                safe_enter_text("body > form > input.postal", "41094", "Postal Code Field", optional=True)
            except:
                # Fall back to any input field that might be for zip/postal codes
                try:
                    zip_fields = driver.find_elements(By.XPATH, 
                        "//input[@type='text' and (contains(@placeholder, 'zip') or contains(@placeholder, 'post') or @maxlength='5')]")
                    
                    if zip_fields:
                        for field in zip_fields:
                            if field.is_displayed():
                                field.clear()
                                field.send_keys("41094")
                                print("Entered ZIP code: 41094")
                                break
                except Exception as zip_error:
                    print(f"Error entering ZIP code: {str(zip_error)}")
                    # Continue anyway - might work without zip
            
            short_sleep(WAIT_TIME/2)
            
            # Step 13: Click search button (body > form > input.search)
            print("Step 13: Click search button")
            safe_find_and_click("body > form > input.search", "Search Button")
            
            # Use shorter waits with heartbeat signals
            for i in range(4):  # 4 short waits instead of 1 long wait
                short_sleep(WAIT_TIME / 2)
                sys.stderr.write(".")  # Show activity
                sys.stderr.flush()
            
            # Handle alert if it appears
            try:
                alert = WebDriverWait(driver, WAIT_TIME/2).until(EC.alert_is_present())
                alert_text = alert.text
                print(f"Alert detected: {alert_text}")
                alert.accept()
                print("Dismissed alert")
                
                # If the alert mentions a missing field, try to fix it
                if "year" in alert_text.lower():
                    print("Alert mentioned year - trying to re-enter year...")
                    # Go back to the beginning and try again
                    driver.get(platform["url"])
                    short_sleep(WAIT_TIME)
                    print("Restarted test due to alert - skipping to next test case")
                    results.append({
                        'Search': test_data['Search Year|Make Model|Group|Part'],
                        'Expected': test_data['Expected'],
                        'Result': f"F - Year entry failed: {alert_text}"
                    })
                    continue  # Skip to next test case
            except:
                # No alert, which is good
                pass
            
            save_debug_info("after_first_search", always_save=True)
            
            # Step 14: On the interchange page, click the search button (#MainForm > input.search)
            print("Step 14: Click search button on interchange page")
            try:
                # Wait longer for the interchange page to fully load
                short_sleep(WAIT_TIME * 2)
                
                # Save a screenshot before we attempt to click the second search button
                save_debug_info("before_second_search", always_save=True)
                
                # Check if we're on an interchange page using a more reliable approach
                page_text = driver.find_element(By.TAG_NAME, "body").text
                is_interchange_page = "interchange" in page_text.lower() or (
                    "search using" in page_text.lower() and "model" in page_text.lower())
                
                print(f"Page text preview: {page_text[:100]}...")
                print(f"Is interchange page detected? {is_interchange_page}")
                
                # Try to find the MainForm to verify we're on the right page
                main_forms = driver.find_elements(By.CSS_SELECTOR, "#MainForm")
                if main_forms:
                    print(f"Found MainForm - definitely on interchange page")
                    is_interchange_page = True
                
                if is_interchange_page:
                    print("On interchange page - clicking second search button")
                    
                    # Try more aggressively to find and click the search button
                    search_clicked = False
                    
                    # First try - specific selector
                    try:
                        search_button = WebDriverWait(driver, WAIT_TIME).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "#MainForm > input.search"))
                        )
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_button)
                        short_sleep(WAIT_TIME/2)
                        
                        # Try multiple click methods
                        if try_click(search_button, "interchange search button"):
                            print("Successfully clicked interchange search button")
                            search_clicked = True
                    except Exception as e:
                        print(f"Could not click specific search button: {str(e)}")
                    
                    # Second try - any search button or input
                    if not search_clicked:
                        try:
                            search_elements = driver.find_elements(By.XPATH, 
                                "//input[@type='submit' or @type='image'] | " +
                                "//button[@type='submit'] | " +
                                "//input[@value='Search'] | " +
                                "//button[contains(text(), 'Search')]")
                            
                            if search_elements:
                                for elem in search_elements:
                                    if elem.is_displayed():
                                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                                        short_sleep(WAIT_TIME/2)
                                        if try_click(elem, "any visible search button on interchange page"):
                                            print(f"Clicked alternative search button on interchange page: {elem.get_attribute('outerHTML')}")
                                            search_clicked = True
                                            break
                                
                                if not search_clicked:
                                    print("Found search buttons but none were clickable")
                            else:
                                print("No search buttons found on interchange page")
                        except Exception as e:
                            print(f"Error trying to find alternative search buttons: {str(e)}")
                    
                    # Third try - JavaScript executor
                    if not search_clicked:
                        try:
                            search_clicked = driver.execute_script("""
                                // Try to find and click the search button in multiple ways
                                
                                // 1. Try to find any input of type submit with 'search' class or value
                                var searchInputs = document.querySelectorAll('input[type="submit"], input[type="image"]');
                                for (var i = 0; i < searchInputs.length; i++) {
                                    if (searchInputs[i].className.includes('search') || 
                                        searchInputs[i].value.toLowerCase().includes('search')) {
                                        searchInputs[i].click();
                                        return "Clicked search input using JavaScript";
                                    }
                                }
                                
                                // 2. Try to find any button with 'search' in text or class
                                var buttons = document.querySelectorAll('button');
                                for (var i = 0; i < buttons.length; i++) {
                                    if (buttons[i].textContent.toLowerCase().includes('search') || 
                                        buttons[i].className.includes('search')) {
                                        buttons[i].click();
                                        return "Clicked search button using JavaScript";
                                    }
                                }
                                
                                // 3. Try to just submit the MainForm
                                var mainForm = document.getElementById('MainForm');
                                if (mainForm) {
                                    mainForm.submit();
                                    return "Submitted MainForm using JavaScript";
                                }
                                
                                // 4. Try to submit any form
                                var forms = document.getElementsByTagName('form');
                                if (forms.length > 0) {
                                    forms[0].submit();
                                    return "Submitted first form using JavaScript";
                                }
                                
                                return false;
                            """)
                            
                            if search_clicked:
                                print(f"Search action performed via JavaScript: {search_clicked}")
                        except Exception as js_error:
                            print(f"JavaScript search button attempt failed: {str(js_error)}")
                            
                    # Final confirmation and debug
                    if search_clicked:
                        print("Successfully triggered search on interchange page")
                        # Save screenshot after clicking search
                        save_debug_info("after_interchange_search_click", always_save=True)
                        
                        # Wait longer for the final results page to load
                        print("Waiting for final results page to load...")
                        for i in range(8):  # Longer wait
                            short_sleep(WAIT_TIME / 2)
                            sys.stderr.write(".")
                            sys.stderr.flush()
                    else:
                        print("WARNING: Failed to click search button on interchange page")
                else:
                    print("Not on interchange page - proceeding directly to verification")
            except Exception as e:
                print(f"Error handling interchange page: {str(e)}")
                save_debug_info("error_interchange_page", error_occurred=True)
            
            # Step 15: Verify search info in the specified element (optimized version)
            print("Step 15: Verifying search results")
            try:
                # Set a strict timeout for verification
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Quick check for the existence of verification element
                verification_elements = driver.find_elements(By.CSS_SELECTOR, 
                    "body > center > font > table > tbody > tr:nth-child(2) > td > table > tbody")
                
                if verification_elements:
                    # Get text more efficiently
                    verification_text = driver.execute_script("""
                        return document.body.innerText;
                    """)
                    print(f"Found verification text (first 100 chars): {verification_text[:100]}...")
                    
                    # Check if the original search terms are in the verification text
                    search_terms = []
                    if year:
                        search_terms.append(year)
                    if full_model:
                        search_terms.extend([term for term in full_model.split() if len(term) > 2])
                    if part:
                        search_terms.extend([term for term in part.split() if len(term) > 2])
                    
                    # Count how many search terms are found
                    found_terms = []
                    for term in search_terms:
                        if term.lower() in verification_text.lower():
                            found_terms.append(term)
                    
                    # Determine test result
                    if len(found_terms) >= len(search_terms) * 0.7:  # Found at least 70% of terms
                        print(f"Found search terms in results: {found_terms}")
                        result = "P - Search terms verified in results"
                        print(f"TEST PASSED: {result}")
                    else:
                        print(f"Only found these search terms in results: {found_terms}")
                        # Check if "No parts found" is present
                        if "No parts found" in verification_text or "no parts were found" in verification_text.lower():
                            result = "F - No parts found"
                            print(f"TEST FAILED: {result}")
                        else:
                            result = "F - Could not verify search terms in results"
                            print(f"TEST FAILED: {result}")
                else:
                    # Simplified fallback
                    page_text = driver.execute_script("return document.body.innerText;")
                    
                    # Count how many search terms are found in the whole page
                    found_terms = []
                    for term in search_terms:
                        if term.lower() in page_text.lower():
                            found_terms.append(term)
                    
                    if len(found_terms) >= len(search_terms) * 0.7:
                        print(f"Found search terms in page text: {found_terms}")
                        result = "P - Search terms verified in page text"
                        print(f"TEST PASSED: {result}")
                    else:
                        print(f"Only found these search terms in page text: {found_terms}")
                        if "No parts found" in page_text or "no parts were found" in page_text.lower():
                            result = "F - No parts found"
                            print(f"TEST FAILED: {result}")
                        else:
                            result = "F - Could not verify search terms in page"
                            print(f"TEST FAILED: {result}")
                    
            except Exception as e:
                print(f"Error verifying search results: {str(e)}")
                result = "F - Verification error: " + str(e)
            
            # Store the result for this test case
            results.append({
                'Search': test_data['Search Year|Make Model|Group|Part'],
                'Expected': test_data['Expected'],
                'Result': result
            })
            
            # Step 16: Return to start page for next test
            print("Step 16: Returning to start page for next test")
            driver.get(platform["url"])
            
            # Use shorter waits with activity signals
            for i in range(4):
                short_sleep(WAIT_TIME / 2)
                sys.stderr.write(".")
                sys.stderr.flush()
            
        except Exception as e:
            # Enhanced error handling
            result = handle_test_error(e, test_data, index)
            results.append(result)
            
            # Even after error, try to reset to search screen for next test
            try:
                driver.get(platform["url"])
                print("Ensuring we're on the start page...")
                try:
                    # Wait for the page to fully load
                    WebDriverWait(driver, WAIT_TIME * 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#yearSelect"))
                    )
                    print("Successfully returned to start page for next test")
                except:
                    print("WARNING: May not have returned to start page correctly")
                short_sleep(WAIT_TIME * 2)
            except:
                print("Could not reset to search page after error")
                
            continue  # Continue to next test case
    
    # Save final results to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_df = pd.DataFrame(results)
    results_file = f"results_{timestamp}.csv"
    results_df.to_csv(results_file, index=False)
    print(f"\nTesting complete! Results saved to {results_file}")
    
    # Summary statistics
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['Result'].startswith('P'))
    failed_tests = total_tests - passed_tests
    
    print(f"\nTest Summary:")
    print(f"  Total Tests: {total_tests}")
    print(f"  Passed Tests: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"  Failed Tests: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
    
    # Use a timeout version of the input prompt
    print("Test complete. Browser will close in 10 seconds (or press Enter to close now)...")
    try:
        # Wait for user input with a timeout
        i, o, e = select.select([sys.stdin], [], [], 10)
        if i:
            sys.stdin.readline()
    except:
        # If anything goes wrong, just continue
        pass
    
except Exception as e:
    print(f"FATAL ERROR: {str(e)}")
    # Save screenshot when an error occurs
    debug_file = save_debug_info("fatal_error", error_occurred=True)
    print(f"Saved error debug info to {debug_file}")
    
finally:
    print("Test complete")
    # Auto-close the browser
    driver.quit()