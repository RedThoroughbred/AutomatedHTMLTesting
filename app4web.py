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

try:
    # Load all test cases
    test_cases = pd.read_csv(args.test_set)
    print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
    
    results = []

    # Process each test case
    for index, test_data in test_cases.iterrows():
        print(f"\n{'='*80}\nTesting case {index+1}/{len(test_cases)}: {test_data['Search Year|Make Model|Group|Part']}\n{'='*80}")
        
        try:
            # Get the platform config (using only the first platform for now)
            platform = platforms_to_test[0]
            
            # Navigate to the configured URL
            driver.get(platform["url"])
            print(f"Opened website: {platform['url']}")
            
            # Wait for the page to load
            time.sleep(WAIT_TIME)
            
            # Parse test data
            parts = test_data['Search Year|Make Model|Group|Part'].split('|')
            year = parts[0]
            model = parts[1]
            part_group = parts[2] if len(parts) > 2 else ""
            part = parts[3] if len(parts) > 3 else ""  # Assuming format is Year|Make Model|Group|Part
            
            # Check for special 'ABSENT' expected result
            expected_result = "PRESENT"  # Default
            if 'ExpectedResult' in test_data:
                expected_result = test_data['ExpectedResult']
            
            # Store the original search criteria for verification later
            original_search = f"{year} {model} {part}"
            print(f"Original search criteria: {original_search}")
            print(f"Expected result: {expected_result}")
            
            # Take a screenshot of the initial page
            save_debug_info("initial_page", always_save=True)
            
            # ===== 1. Click and set Year =====
            print(f"Selecting year: {year}")
            
            # First click the year dropdown
            year_dropdown = WebDriverWait(driver, WAIT_TIME).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#yearSelect"))
            )
            try_click(year_dropdown, "year dropdown")
            time.sleep(WAIT_TIME)  # Wait longer for dropdown to fully appear
            
            # Handle alert if it appears
            try:
                alert = Alert(driver)
                alert_text = alert.text
                print(f"Alert detected: {alert_text}")
                alert.dismiss()
                time.sleep(WAIT_TIME/2)
            except:
                pass
            
            # Now find and click the specific year
            try:
                # Take a screenshot to see the dropdown options
                save_debug_info("year_dropdown_open", always_save=True)
                
                # First, try to find the year as a direct link
                year_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{year}')]")
                
                if year_elements:
                    for elem in year_elements:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(WAIT_TIME/2)
                            try_click(elem, f"year {year}")
                            print(f"Clicked year: {year}")
                            time.sleep(WAIT_TIME)
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
                        # Try one more approach with JavaScript
                        print("Using direct JavaScript approach for year")
                        
                        # First query the page to see what elements might be available
                        elements_info = driver.execute_script("""
                            var elements = [];
                            var yearOptions = document.querySelectorAll('a, li, div, option');
                            for (var i=0; i < yearOptions.length; i++) {
                                if (yearOptions[i].textContent.includes('""" + year + """')) {
                                    elements.push({
                                        tag: yearOptions[i].tagName,
                                        text: yearOptions[i].textContent.trim(),
                                        id: yearOptions[i].id,
                                        className: yearOptions[i].className
                                    });
                                }
                            }
                            return elements;
                        """)
                        
                        print(f"Found {len(elements_info)} possible year elements: {elements_info[:3]}")
                        
                        # Try clicking these elements
                        for info in elements_info:
                            if info.get('tag') and info.get('text') and year in info.get('text'):
                                try:
                                    if info.get('id'):
                                        elem = driver.find_element(By.ID, info.get('id'))
                                    elif info.get('className'):
                                        elems = driver.find_elements(By.CLASS_NAME, info.get('className'))
                                        elem = next((e for e in elems if year in e.text), None)
                                    else:
                                        continue
                                        
                                    if elem and elem.is_displayed():
                                        try_click(elem, f"year by element info: {info}")
                                        print(f"Clicked year using element info")
                                        time.sleep(WAIT_TIME)
                                        break
                                except:
                                    continue
                            
                        # Last resort - try to click anything with the year
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
                        time.sleep(WAIT_TIME)
            except Exception as e:
                print(f"Error selecting year: {str(e)}")
                # Continue anyway - the website might allow us to proceed
            
            # Save a screenshot after year selection attempt
            save_debug_info("after_year_selection", always_save=True)
            
            # ===== 2. Click and set Make/Model (split into separate steps) =====
            # First extract make and model separately
            model_parts = model.split()
            if len(model_parts) >= 2:
                make = model_parts[0]  # First word is likely the make
                model_name = ' '.join(model_parts[1:])  # Rest is the model
            else:
                make = model  # If only one word, assume it's both make and model
                model_name = ""
            
            print(f"Selecting make: {make}")
            
            # First click the vehicle dropdown to select make
            try:
                vehicle_dropdown = WebDriverWait(driver, WAIT_TIME).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#vehicleSelect"))
                )
                try_click(vehicle_dropdown, "make dropdown")
                time.sleep(WAIT_TIME)
                
                # Take a screenshot to see dropdown options
                save_debug_info("make_dropdown_open", always_save=True)
                
                # Try to find and click the make
                make_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{make}')]")
                if make_elements:
                    for elem in make_elements:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(WAIT_TIME/2)
                            try_click(elem, f"make {make}")
                            print(f"Clicked make: {make}")
                            time.sleep(WAIT_TIME)
                            break
                else:
                    # Try JavaScript to find and click the make
                    driver.execute_script("""
                        var make = arguments[0];
                        var elements = Array.from(document.querySelectorAll('a, div, option, li, button, span'));
                        for (var i=0; i < elements.length; i++) {
                            if (elements[i].textContent.indexOf(make) >= 0 && elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                                elements[i].scrollIntoView(true);
                                elements[i].click();
                                return true;
                            }
                        }
                        return false;
                    """, make)
                    print(f"Used JavaScript to click make: {make}")
                    time.sleep(WAIT_TIME)
            except Exception as e:
                print(f"Error selecting make: {str(e)}")
            
            # Save a screenshot after make selection
            save_debug_info("after_make_selection", always_save=True)
            
            # Now select model if needed
            if model_name:
                print(f"Selecting model: {model_name}")
                
                try:
                    # Take a screenshot before model selection
                    save_debug_info("before_model_selection", always_save=True)
                    
                    # Try to find and click the model
                    model_elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{model_name}')]")
                    if model_elements:
                        for elem in model_elements:
                            if elem.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                                time.sleep(WAIT_TIME/2)
                                try_click(elem, f"model {model_name}")
                                print(f"Clicked model: {model_name}")
                                time.sleep(WAIT_TIME)
                                break
                    else:
                        # Try JavaScript to find and click the model
                        driver.execute_script("""
                            var model = arguments[0];
                            var elements = Array.from(document.querySelectorAll('a, div, option, li, button, span'));
                            for (var i=0; i < elements.length; i++) {
                                if (elements[i].textContent.indexOf(model) >= 0 && elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                                    elements[i].scrollIntoView(true);
                                    elements[i].click();
                                    return true;
                                }
                            }
                            return false;
                        """, model_name)
                        print(f"Used JavaScript to click model: {model_name}")
                        time.sleep(WAIT_TIME)
                except Exception as e:
                    print(f"Error selecting model: {str(e)}")
            
            # Save a screenshot after model selection
            save_debug_info("after_model_selection", always_save=True)
            
            # ===== 3. Click Part Type =====
            print(f"Selecting part group: {part_group}")
            
            # Convert part_group to a likely ID format (e.g., "Axle & Brakes" -> "AxleBrakes")
            part_group_id = part_group.replace("&", "").replace(" ", "")
            part_group_selector = f"#select{part_group_id}"
            
            try:
                # Try to click the part group
                part_group_element = WebDriverWait(driver, WAIT_TIME).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, part_group_selector))
                )
                try_click(part_group_element, f"part group {part_group}")
                time.sleep(WAIT_TIME/2)
            except:
                # Try to find any element containing the part group text
                try:
                    part_group_elements = driver.find_elements(By.XPATH, 
                                                            f"//a[contains(text(), '{part_group}')] | //button[contains(text(), '{part_group}')]")
                    
                    if part_group_elements:
                        try_click(part_group_elements[0], f"part group by text {part_group}")
                        print(f"Clicked part group by text: {part_group}")
                        time.sleep(WAIT_TIME/2)
                    else:
                        # Try to find it by partial text
                        part_words = [w for w in part_group.split() if len(w) > 3]
                        for word in part_words:
                            elements = driver.find_elements(By.XPATH, f"//a[contains(text(), '{word}')] | //button[contains(text(), '{word}')]")
                            if elements:
                                try_click(elements[0], f"part group by keyword {word}")
                                print(f"Clicked part group by keyword: {word}")
                                time.sleep(WAIT_TIME/2)
                                break
                        else:
                            raise Exception(f"Could not find part group {part_group}")
                except Exception as e:
                    print(f"Part group selection failed: {str(e)}")
                    raise Exception(f"Could not select part group {part_group}")
            
            # Save a screenshot after part group selection
            save_debug_info("after_part_group_selection", always_save=True)
            
            # ===== 4. Select Part =====
            # For part like "Latch (Liftgate)", split into main part and qualifier
            print(f"Selecting part: {part}")
            
            # Extract the main part name and qualifier if present
            part_main = part
            part_qualifier = ""
            if '(' in part:
                part_main = part.split('(')[0].strip()
                part_qualifier = part.split('(')[1].split(')')[0].strip()
                print(f"Split part into main: '{part_main}' and qualifier: '{part_qualifier}'")
            
            # Wait longer for part options to become visible
            time.sleep(WAIT_TIME * 2)
            
            # Take a screenshot to see available parts
            save_debug_info("before_part_selection", always_save=True)
            
            # Log all clickable elements on the page to help debug
            clickable_elements = driver.find_elements(By.XPATH, "//a | //button | //div[@onclick] | //span[@onclick]")
            visible_clickable = [e for e in clickable_elements if e.is_displayed()]
            print(f"Found {len(visible_clickable)} visible clickable elements. First 10 texts:")
            for i, elem in enumerate(visible_clickable[:10]):
                print(f"  {i+1}: {elem.text.strip() or '[No text]'}")
            
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
                            time.sleep(WAIT_TIME)
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
                                time.sleep(WAIT_TIME)
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
                                time.sleep(WAIT_TIME)
                                break
                    else:
                        print(f"Could not find qualifier '{part_qualifier}', continuing with main part only")
                
                # If we still haven't found the part, try JavaScript with the full part name
                if not part_found:
                    driver.execute_script("""
                        var partName = arguments[0];
                        var elements = Array.from(document.querySelectorAll('a, div, span, button, li'));
                        for (var i=0; i < elements.length; i++) {
                            if (elements[i].textContent.indexOf(partName) >= 0 && elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                                console.log("Found element: " + elements[i].tagName + " - " + elements[i].textContent);
                                elements[i].scrollIntoView(true);
                                elements[i].click();
                                return true;
                            }
                        }
                        return false;
                    """, part)
                    print(f"Used JavaScript to try clicking part: {part}")
                    selected_part = part
                    part_found = True
                    time.sleep(WAIT_TIME)
            except Exception as e:
                print(f"Error during part selection: {str(e)}")
                
                # Last-ditch effort - use JavaScript to try finding any element with the part name
                try:
                    part_words = [w for w in part.split() if len(w) > 2]
                    for word in part_words:
                        found = driver.execute_script("""
                            var word = arguments[0];
                            var elements = Array.from(document.querySelectorAll('a, div, span, button, li'));
                            for (var i=0; i < elements.length; i++) {
                                if (elements[i].textContent.indexOf(word) >= 0 && elements[i].offsetWidth > 0 && elements[i].offsetHeight > 0) {
                                    console.log("Found element with keyword: " + elements[i].tagName + " - " + elements[i].textContent);
                                    elements[i].scrollIntoView(true);
                                    elements[i].click();
                                    return elements[i].textContent;
                                }
                            }
                            return false;
                        """, word)
                        
                        if found:
                            print(f"Used JavaScript to click element with keyword '{word}': {found}")
                            selected_part = found
                            part_found = True
                            time.sleep(WAIT_TIME)
                            break
                except Exception as js_error:
                    print(f"JavaScript part selection failed: {str(js_error)}")
            
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
            
            try:
                # Try to find the search button
                search_button = WebDriverWait(driver, WAIT_TIME).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "body > form > input.search"))
                )
                try_click(search_button, "search button")
                time.sleep(WAIT_TIME)
            except:
                # Try alternative search button approaches
                try:
                    search_elements = driver.find_elements(By.XPATH, 
                                                         "//input[@type='submit'] | //button[@type='submit'] | //input[@value='Search'] | //button[contains(text(), 'Search')]")
                    
                    if search_elements:
                        for element in search_elements:
                            if element.is_displayed():
                                try_click(element, "alternative search button")
                                print("Clicked alternative search button")
                                time.sleep(WAIT_TIME)
                                break
                        else:
                            # Try to submit the form
                            forms = driver.find_elements(By.TAG_NAME, "form")
                            if forms:
                                for form in forms:
                                    try:
                                        form.submit()
                                        print("Submitted form")
                                        time.sleep(WAIT_TIME)
                                        break
                                    except:
                                        continue
                            else:
                                raise Exception("Could not find search button or form to submit")
                    else:
                        raise Exception("Could not find any search button")
                except Exception as e:
                    print(f"Search button click failed: {str(e)}")
                    raise Exception("Could not click search button")
            
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
                    interchange_search_button = WebDriverWait(driver, WAIT_TIME).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "#MainForm > input.search"))
                    )
                    try_click(interchange_search_button, "interchange search button")
                    time.sleep(WAIT_TIME * 2)
                except:
                    # Try alternative search buttons
                    try:
                        search_elements = driver.find_elements(By.XPATH, 
                                                             "//input[@type='submit'] | //button[@type='submit'] | //input[@value='Search'] | //button[contains(text(), 'Search')]")
                        
                        if search_elements:
                            for element in search_elements:
                                if element.is_displayed():
                                    try_click(element, "alternative interchange search button")
                                    print("Clicked alternative interchange search button")
                                    time.sleep(WAIT_TIME * 2)
                                    break
                        else:
                            print("Could not find interchange search button")
                    except Exception as e:
                        print(f"Interchange search button click failed: {str(e)}")
            
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
                main_part_terms = [term.lower() for term in selected_part.split() if len(term) > 2 and term.lower() not in ["display", "image", "with", "w"]]
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
            
            # Store the result for this test case
            results.append({
                'Search': test_data['Search Year|Make Model|Group|Part'],
                'Expected': test_data['Expected'],
                'Result': result
            })
            
            # Reset for next test
            try:
                driver.get(platform["url"])
                print("Navigated back to start for next test")
                time.sleep(WAIT_TIME * 2)
            except Exception as e:
                print(f"Error returning to start: {str(e)}")
            
        except Exception as e:
            # Enhanced error handling
            result = handle_test_error(e, test_data, index)
            results.append(result)
            
            # Even after error, try to reset to search screen for next test
            try:
                driver.get(platform["url"])
                time.sleep(WAIT_TIME * 2)
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
    
    # Keep browser open for inspection
    input("Press Enter to close the browser...")
    
except Exception as e:
    print(f"FATAL ERROR: {str(e)}")
    # Save screenshot when an error occurs
    debug_file = save_debug_info("fatal_error", error_occurred=True)
    print(f"Saved error debug info to {debug_file}")
    
finally:
    print("Test complete")
    # Uncomment to auto-close
    # driver.quit()