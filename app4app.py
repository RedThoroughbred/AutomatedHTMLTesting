import json
import pandas as pd
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
from datetime import datetime
import re
import os

# Command line arguments for flexible execution
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
with open('config4app.json', 'r') as f:
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
    """Save screenshot and HTML source for debugging
    only save for errors or if always_save is True"""
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

def analyze_results_page():
    """Analyze the current page for parts"""
    # Look for various element types that might contain results
    tables = driver.find_elements(By.TAG_NAME, "table")
    divs = driver.find_elements(By.XPATH, "//div[contains(@class, 'result') or contains(@class, 'part') or contains(@class, 'item')]")
    list_items = driver.find_elements(By.TAG_NAME, "li")
    
    print(f"Found: {len(tables)} tables, {len(divs)} potential result divs, {len(list_items)} list items")
    
    # Extract text from various elements to look for part information
    result_texts = []
    
    # Try tables first (most common for part listings)
    if tables:
        for i, table in enumerate(tables):
            table_text = table.text.strip()
            if table_text and len(table_text) > 20:  # Skip empty or very small tables
                print(f"Table {i} content preview: {table_text[:100]}...")
                result_texts.append(table_text)
    
    if result_texts:
        print(f"Found {len(result_texts)} result tables")
        return True, []  # Return empty issues list since we're not checking ordering
    else:
        print("No parts found in page")
        return False, []

def handle_interchange_page():
    """Special handler for the interchange page"""
    print("Using specialized interchange page handler...")
    
    # Try the exact CSS selector for the search button provided
    try:
        specific_button = driver.find_element(By.CSS_SELECTOR, "body > table > tbody > tr:nth-child(2) > td > form > center > input[type=image]")
        print("Found specific search button by CSS selector")
        specific_button.click()
        print("Clicked search button using CSS selector")
        time.sleep(WAIT_TIME)
        return True
    except Exception as e:
        print(f"Could not click specific button: {str(e)}")
    
    # First, try to directly click any image submit buttons
    try:
        image_buttons = driver.find_elements(By.XPATH, "//input[@type='image']")
        if image_buttons:
            print(f"Found {len(image_buttons)} image buttons")
            for button in image_buttons:
                src = button.get_attribute("src") or ""
                if "search" in src.lower() or "button" in src.lower():
                    print(f"Found likely search image: {src}")
                    button.click()
                    print("Clicked image button")
                    time.sleep(WAIT_TIME)
                    return True
            
            # If no specific match, try the first image button
            image_buttons[0].click()
            print("Clicked first image button")
            time.sleep(WAIT_TIME)
            return True
    except Exception as e:
        print(f"Error with image buttons: {str(e)}")
    
    # Try to find and click radio buttons then submit the form
    try:
        # Find all forms
        forms = driver.find_elements(By.TAG_NAME, "form")
        if forms:
            for form in forms:
                # Look for radio buttons in the form
                radio_buttons = form.find_elements(By.XPATH, ".//input[@type='radio']")
                if radio_buttons:
                    print(f"Found {len(radio_buttons)} radio buttons")
                    # Click the first radio button (usually for "Non-Interchange search using only...")
                    radio_buttons[0].click()
                    print("Clicked radio button for search option")
                    
                    # Now look for image inputs in this form
                    image_inputs = form.find_elements(By.XPATH, ".//input[@type='image']")
                    if image_inputs:
                        image_inputs[0].click()
                        print("Clicked image button in form after radio selection")
                        time.sleep(WAIT_TIME)
                        return True
                    
                    # If no image inputs, try to submit the form directly
                    try:
                        form.submit()
                        print("Submitted form after radio selection")
                        time.sleep(WAIT_TIME)
                        return True
                    except:
                        print("Could not submit form")
    except Exception as e:
        print(f"Error with form handling: {str(e)}")
    
    # JavaScript approach to click any image input
    try:
        driver.execute_script("""
            var images = document.querySelectorAll('input[type="image"]');
            if (images.length > 0) {
                images[0].click();
                return true;
            }
            return false;
        """)
        print("Clicked image button via JavaScript")
        time.sleep(WAIT_TIME)
        return True
    except:
        pass
    
    return False

def verify_top_right_details(expected_year, expected_model, expected_part, actual_part):
    """Verify the part details in the top-right corner match what was searched"""
    try:
        # The top-right details are typically in a table cell or div
        # First, look for a table containing the make/model information
        details_elements = driver.find_elements(By.XPATH, 
            "//td[contains(text(), 'Make/Model:') or contains(text(), 'Part:')]")
        
        # If we can't find it that way, look for text containing both year and model
        if not details_elements:
            details_elements = driver.find_elements(By.XPATH, 
                f"//td[contains(text(), '{expected_year}') and contains(text(), '{expected_model}')]")
        
        # If still not found, look more broadly
        if not details_elements:
            # Try to find elements with the Part: prefix
            part_elements = driver.find_elements(By.XPATH, "//td[contains(text(), 'Part:')]")
            make_model_elements = driver.find_elements(By.XPATH, "//td[contains(text(), 'Make/Model:')]")
            
            details_elements = part_elements + make_model_elements
        
        # Get all the text from the detail elements
        detail_texts = [elem.text for elem in details_elements]
        full_detail_text = " ".join(detail_texts)
        
        if detail_texts:
            print(f"Found part details: {detail_texts[:2]}")  # Show just the first couple for brevity
            
            # Check if all expected values are present
            year_verified = expected_year in full_detail_text
            
            # Check the model - allow for partial matching for flexibility
            model_parts = expected_model.lower().split()
            model_verified = all(part in full_detail_text.lower() for part in model_parts if len(part) > 2)
            
            # For part verification, extract core keywords from the selected part
            # First, use the actual selected part name for verification
            core_part_terms = []
            
            # Try to extract the main part name without display/image qualifiers
            if '(' in actual_part:
                main_part = actual_part.split('(')[0].strip().lower()
                if main_part:
                    core_part_terms = [term for term in main_part.split() if len(term) > 2]
            else:
                core_part_terms = [term for term in actual_part.lower().split() if len(term) > 2 
                               and term not in ['display', 'image', 'with']]
            
            # If we couldn't extract any meaningful terms, use the whole part name
            if not core_part_terms:
                core_part_terms = [term for term in actual_part.lower().split() if len(term) > 2]
                
            part_verified = all(term in full_detail_text.lower() for term in core_part_terms)
            
            # Check if the original requested part matches what we found
            part_match = False
            requested_part_terms = [term.lower() for term in expected_part.split() if len(term) > 2 
                                  and term.lower() not in ['display', 'image', 'with', 'w']]
            actual_part_terms = [term.lower() for term in actual_part.split() if len(term) > 2 
                               and term.lower() not in ['display', 'image', 'with', 'w']]
            
            # Check if all important terms from the requested part are in the actual part
            if any(term in ' '.join(actual_part_terms) for term in requested_part_terms):
                part_match = True
            
            if year_verified and model_verified and part_verified:
                result_msg = "✓ SUCCESS: Part details verified in top-right corner"
                if not part_match:
                    result_msg += f" (Warning: Selected '{actual_part}' instead of '{expected_part}')"
                print(result_msg)
                return True, None, part_match
            else:
                missing = []
                if not year_verified: missing.append("year")
                if not model_verified: missing.append("model")
                if not part_verified: missing.append("part")
                error = f"Missing {', '.join(missing)} in details"
                print(f"✗ ERROR: {error}")
                return False, error, part_match
        else:
            error = "Could not find part details in page"
            print(f"✗ ERROR: {error}")
            return False, error, False
            
    except Exception as e:
        error = f"Error verifying part details: {str(e)}"
        print(f"✗ ERROR: {error}")
        return False, error, False

def print_available_models():
    """Print all available models in the dropdown"""
    try:
        model_select = Select(driver.find_element(By.CSS_SELECTOR, "#model"))
        options = [option.text for option in model_select.options]
        print("Available models:")
        for option in options:
            print(f"  - {option}")
        return options
    except Exception as e:
        print(f"Error getting available models: {str(e)}")
        return []

def summarize_dropdown_issues(dropdown_issues):
    """Create a concise summary of dropdown issues"""
    if not dropdown_issues:
        return ""
        
    # Count issues by type
    duplicate_count = sum(1 for issue in dropdown_issues if "Duplicate dropdown option" in issue)
    order_count = sum(1 for issue in dropdown_issues if "out of order" in issue)
    
    # Create summary
    summary_parts = []
    if duplicate_count > 0:
        summary_parts.append(f"{duplicate_count} duplicate dropdown options")
    if order_count > 0:
        summary_parts.append(f"{order_count} dropdown ordering issues")
    
    return f" ({', '.join(summary_parts)})" if summary_parts else ""

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

def handle_login(platform):
    """Handle login if site requires it"""
    if platform.get("requires_login", False):
        try:
            print(f"Logging in to {platform['name']}...")
            # Find and fill username field
            username_field = driver.find_element(By.CSS_SELECTOR, platform["login_selectors"]["username_field"])
            username_field.send_keys(platform["username"])
            
            # Find and fill password field
            password_field = driver.find_element(By.CSS_SELECTOR, platform["login_selectors"]["password_field"])
            password_field.send_keys(platform["password"])
            
            # Click login button
            login_button = driver.find_element(By.CSS_SELECTOR, platform["login_selectors"]["login_button"])
            try_click(login_button, "login button")
            
            # Wait for login to complete
            time.sleep(WAIT_TIME)
            print("Login completed")
            return True
        except Exception as e:
            print(f"Login error: {str(e)}")
            return False
    else:
        return True  # No login needed

try:
    # Load all test cases
    test_cases = pd.read_csv(args.test_set)
    print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
    
    results = []
    all_dropdown_issues = []  # Track dropdown issues for reporting

    # Process each test case
    for index, test_data in test_cases.iterrows():
        print(f"\n{'='*80}\nTesting case {index+1}/{len(test_cases)}: {test_data['Search Year|Make Model|Group|Part']}\n{'='*80}")
        
        try:
            # Get the platform config (using only the first platform for now)
            platform = platforms_to_test[0]
            
            # Navigate to the configured URL
            driver.get(platform["url"])
            print(f"Opened website: {platform['url']}")
            
            # Handle login if required
            if not handle_login(platform):
                raise Exception(f"Failed to log in to {platform['name']}")
            
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
            
            # 1. Select Year
            print(f"Selecting year: {year}")
            year_select = Select(driver.find_element(By.CSS_SELECTOR, "#year"))
            year_select.select_by_visible_text(year)
            
            # Wait for make/model dropdown to populate
            time.sleep(WAIT_TIME/2)  # Shorter wait time
            
            # 2. Select Make/Model
            print(f"Selecting model: {model}")
            try:
                model_select = Select(driver.find_element(By.CSS_SELECTOR, "#model"))
                model_select.select_by_visible_text(model)
            except Exception as e:
                print(f"Error selecting model '{model}': {str(e)}")
                # Print available models for debugging
                available_models = print_available_models()
                
                # Try to find a close match
                found_match = False
                model_lower = model.lower()
                for available_model in available_models:
                    if model_lower in available_model.lower():
                        print(f"Found similar model: {available_model}")
                        model_select.select_by_visible_text(available_model)
                        model = available_model  # Update model for later verification
                        found_match = True
                        break
                
                if not found_match:
                    raise Exception(f"Could not find model '{model}' or a similar match")
            
            # Wait for part dropdown to populate
            time.sleep(WAIT_TIME/2)  # Shorter wait time
            
            # 3. Enter ZIP code
            try:
                print("Looking for ZIP code field...")
                zip_field = driver.find_element(By.NAME, "userZip")
                zip_field.clear()
                zip_field.send_keys("41094")
                print("Entered ZIP code: 41094")
            except:
                print("ZIP code field not found, will handle alert if it appears")
            
            # 4. Select Part
            print(f"Selecting part: {part}")
            part_selector = "body > div:nth-child(1) > table:nth-child(2) > tbody > tr:nth-child(2) > td:nth-child(2) > table > tbody > tr:nth-child(2) > td > center > table > tbody > tr:nth-child(3) > td:nth-child(2) > select"
            part_select = Select(driver.find_element(By.CSS_SELECTOR, part_selector))
            
            # Check if we expect the part to be ABSENT
            if expected_result == "ABSENT":
                part_options = [option.text for option in part_select.options]
                if part not in part_options:
                    print(f"✓ SUCCESS: Part '{part}' correctly absent from dropdown")
                    results.append({
                        'Search': test_data['Search Year|Make Model|Group|Part'],
                        'Expected': test_data['Expected'],
                        'Result': f"P - Part correctly absent from dropdown"
                    })
                    continue  # Skip to next test case
                else:
                    print(f"✗ ERROR: Part '{part}' found in dropdown but expected to be absent")
                    results.append({
                        'Search': test_data['Search Year|Make Model|Group|Part'],
                        'Expected': test_data['Expected'],
                        'Result': f"F - Part incorrectly present in dropdown"
                    })
                    continue  # Skip to next test case
            
            # Check for dropdown issues before making selection
            dropdown_issues = check_dropdown_issues(part_select)
            if dropdown_issues:
                print("Dropdown Issues Found:")
                for issue in dropdown_issues[:5]:  # Show just the first few
                    print(f"  - {issue}")
                if len(dropdown_issues) > 5:
                    print(f"  - And {len(dropdown_issues) - 5} more issues")
                
                # Store for final report
                all_dropdown_issues.append((test_data['Search Year|Make Model|Group|Part'], dropdown_issues))
            
            # Get all part options for reference
            all_options = [option.text for option in part_select.options]
            
            # Debug output to see available options
            print(f"Found {len(all_options)} part options. First 10:")
            for i, option in enumerate(all_options[:10]):
                print(f"{i}: {option}")
            
            # Improved part selection logic
            found = False
            part_mismatch_warning = False
            
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
            
            # 5. Click the search button
            print("Clicking search button...")
            search_button = driver.find_element(By.CSS_SELECTOR, platform["selectors"]["search_button"])
            try_click(search_button, "search button")
            
            # 6. Handle alert if it appears
            try:
                print("Checking for alerts...")
                WebDriverWait(driver, WAIT_TIME).until(EC.alert_is_present())
                alert = Alert(driver)
                alert_text = alert.text
                print(f"Alert detected: {alert_text}")
                
                if "zip" in alert_text.lower() or "postal" in alert_text.lower():
                    alert.accept()  # Click OK
                    
                    # Look for ZIP input after alert
                    zip_field = driver.find_element(By.NAME, "userZip")
                    zip_field.clear()
                    zip_field.send_keys("41094")
                    print("Entered ZIP code: 41094")
                    
                    # Try to find a submit button for the ZIP code
                    try:
                        submit_buttons = driver.find_elements(By.XPATH, "//input[@type='submit' or @type='button']")
                        for button in submit_buttons:
                            if button.is_displayed():
                                try_click(button, "ZIP submit button")
                                break
                    except:
                        print("Could not find submit button after ZIP entry")
            except:
                print("No alerts detected")
            
            # Wait for results page to load
            print("Waiting for results page...")
            time.sleep(WAIT_TIME)
            
            # Save debug information if requested
            debug_file = save_debug_info(f"results_page_case_{index+1}")
            
            # Get page title and URL for context
            current_url = driver.current_url
            page_title = driver.title
            print(f"Current page: {page_title} - {current_url}")
            
            # Print some of the page text for debugging
            page_text = driver.find_element(By.TAG_NAME, "body").text
            print(f"Page text preview: {page_text[:200]}...")
            
            # Determine if we're on an interchange page or final results
            is_interchange_page = "interchange" in page_text.lower() or (
                "search using" in page_text.lower() and "model" in page_text.lower()
            )
            print(f"Is this an interchange page? {'Yes' if is_interchange_page else 'No'}")
            
            # If on interchange page, use the special handler
            if is_interchange_page:
                print("On interchange page - using special handler")
                success = handle_interchange_page()
                
                if success:
                    print("Successfully navigated from interchange page")
                else:
                    print("WARNING: Could not navigate from interchange page")
                
                # Save debug info after clicking attempts if requested
                save_debug_info(f"after_interchange_case_{index+1}")
                
                # Wait for the next page to load
                time.sleep(WAIT_TIME)
            
            # Analyze the current page (whether we navigated or not)
            current_url = driver.current_url
            page_title = driver.title
            print(f"Analyzing page: {page_title} - {current_url}")
            
            # Get updated page text
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            # Analyze the page for parts and structure
            found_parts, _ = analyze_results_page()
            
            # Save debug info of the final page if requested
            save_debug_info(f"final_page_case_{index+1}")
            
            # Verify the details in the top-right corner
            details_verified, error, part_match = verify_top_right_details(year, model, part, selected_part)
            
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
            elif details_verified:
                if part_mismatch_warning or not part_match:
                    result = f"P* - Part details verified but selected '{selected_part}' instead of '{part}'"
                else:
                    result = "P - Part details verified"
                # Add a concise summary of dropdown issues if any
                if dropdown_issues:
                    result += summarize_dropdown_issues(dropdown_issues)
                print(f"TEST PASSED: {result}")
            elif search_verification:
                if part_mismatch_warning or not part_match:
                    result = f"P* - Search terms verified but selected '{selected_part}' instead of '{part}'"
                else:
                    result = "P - Search terms verified"
                # Add a concise summary of dropdown issues if any
                if dropdown_issues:
                    result += summarize_dropdown_issues(dropdown_issues)
                print(f"TEST PASSED: {result}")
            else:
                print("TEST FAILED: Could not verify search terms on page")
                result = "F - Could not verify search terms"
            
            # Store the result for this test case
            results.append({
                'Search': test_data['Search Year|Make Model|Group|Part'],
                'Expected': test_data['Expected'],
                'Result': result
            })
            
        except Exception as e:
            # Enhanced error handling
            result = handle_test_error(e, test_data, index)
            results.append(result)
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