import argparse
import json
import os
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Parse command line arguments
parser = argparse.ArgumentParser(description="Custom Website Testing Script")
parser.add_argument("--test-set", help="Path to test cases CSV file", default="test_cases_custom.csv")
parser.add_argument("--url", help="Website URL to test", required=True)
parser.add_argument("--headless", action="store_true", help="Run in headless mode")
parser.add_argument("--save-all-screenshots", action="store_true", help="Save screenshots for all steps")
parser.add_argument("--wait-time", type=float, default=2.0, help="Wait time between actions")
args = parser.parse_args()

# Global variables
WAIT_TIME = args.wait_time
SAVE_ALL_SCREENSHOTS = args.save_all_screenshots
BASE_URL = args.url

# Create screenshots directory
os.makedirs("screenshots", exist_ok=True)

# Setup Chrome options
chrome_options = Options()
chrome_options.add_argument("--window-size=1200,800")
if args.headless:
    print("Running in headless mode")
    chrome_options.add_argument("--headless")

# Initialize the browser
driver = webdriver.Chrome(options=chrome_options)

def save_screenshot(name, always_save=False, error=False):
    """Save screenshot with timestamp"""
    if SAVE_ALL_SCREENSHOTS or always_save or error:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshots/{name}_{timestamp}.png"
        driver.save_screenshot(filename)
        print(f"Screenshot saved: {filename}")
        return filename
    return None

def navigate_to_page(url):
    """Navigate to a URL and wait for it to load"""
    print(f"Navigating to: {url}")
    driver.get(url)
    time.sleep(WAIT_TIME)
    save_screenshot("page_loaded", always_save=True)
    return driver.title

def check_element_exists(selector, by=By.CSS_SELECTOR):
    """Check if an element exists on the page"""
    try:
        driver.find_element(by, selector)
        return True
    except NoSuchElementException:
        return False

def click_element(selector, by=By.CSS_SELECTOR, wait_time=None):
    """Click an element and wait"""
    wait_time = wait_time or WAIT_TIME
    try:
        element = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((by, selector))
        )
        element.click()
        print(f"Clicked element: {selector}")
        time.sleep(wait_time/2)
        save_screenshot("after_click")
        return True
    except Exception as e:
        print(f"Error clicking {selector}: {str(e)}")
        save_screenshot("click_error", error=True)
        return False

def search_for_term(term, search_box_selector="#search", submit_selector="button[type='submit']"):
    """Enter a search term and submit"""
    try:
        search_box = driver.find_element(By.CSS_SELECTOR, search_box_selector)
        search_box.clear()
        search_box.send_keys(term)
        print(f"Entered search term: {term}")
        
        # Click the search button
        submit_button = driver.find_element(By.CSS_SELECTOR, submit_selector)
        submit_button.click()
        print("Clicked search button")
        
        time.sleep(WAIT_TIME)
        save_screenshot("after_search")
        return True
    except Exception as e:
        print(f"Error searching for {term}: {str(e)}")
        save_screenshot("search_error", error=True)
        return False

def verify_text_on_page(text):
    """Check if text appears on the page"""
    page_text = driver.find_element(By.TAG_NAME, "body").text
    if text.lower() in page_text.lower():
        print(f"✓ Text found on page: {text}")
        return True
    else:
        print(f"✗ Text not found on page: {text}")
        return False

def verify_element_exists(selector, by=By.CSS_SELECTOR):
    """Verify an element exists and is visible"""
    try:
        element = WebDriverWait(driver, WAIT_TIME).until(
            EC.visibility_of_element_located((by, selector))
        )
        print(f"✓ Element found: {selector}")
        return True
    except:
        print(f"✗ Element not found: {selector}")
        return False

def run_test_case(test_case):
    """Run a single test case"""
    try:
        # Parse test data from the pipe-delimited format
        parts = test_case['Search Year|Make Model|Group|Part'].split('|')
        
        # These can be interpreted differently based on your site structure
        item1 = parts[0]  # Could be a category, product, etc.
        item2 = parts[1]  # Could be a subcategory, etc.
        item3 = parts[2] if len(parts) > 2 else ""
        item4 = parts[3] if len(parts) > 3 else ""
        
        # First, navigate to the base URL
        navigate_to_page(BASE_URL)
        
        # Example test flow - customize these steps for your site
        if item1:
            # Example: Search for item1
            search_result = search_for_term(item1)
            if not search_result:
                return {"result": "F - Search failed"}
            
            # Verify item1 appears in results
            found = verify_text_on_page(item1)
            if not found:
                return {"result": f"F - '{item1}' not found in search results"}
        
        # Example: Navigate to a specific page using item2
        if item2:
            # Look for a link containing item2 text
            try:
                link = driver.find_element(By.XPATH, f"//a[contains(text(), '{item2}')]")
                link.click()
                print(f"Clicked link containing: {item2}")
                time.sleep(WAIT_TIME)
                save_screenshot(f"after_click_{item2}")
                
                # Verify we're on the right page
                if not verify_text_on_page(item2):
                    return {"result": f"F - '{item2}' page did not load properly"}
            except Exception as e:
                print(f"Error navigating to {item2}: {str(e)}")
                save_screenshot("navigation_error", error=True)
                return {"result": f"F - Navigation error: {str(e)[:100]}"}
        
        # Success case
        return {"result": "P - Test passed"}
        
    except Exception as e:
        print(f"Test case error: {str(e)}")
        save_screenshot("test_error", error=True)
        return {"result": f"F - Error: {str(e)[:100]}"}

def main():
    try:
        # Load test cases
        test_cases = pd.read_csv(args.test_set)
        print(f"Loaded {len(test_cases)} test cases from {args.test_set}")
        
        results = []
        
        # Run each test case
        for index, test_data in test_cases.iterrows():
            print(f"\n{'='*80}\nRunning test case {index+1}/{len(test_cases)}: {test_data['Search Year|Make Model|Group|Part']}\n{'='*80}")
            
            result = run_test_case(test_data)
            
            # Store result
            results.append({
                'Search': test_data['Search Year|Make Model|Group|Part'],
                'Expected': test_data['Expected'],
                'Result': result.get('result', 'Unknown')
            })
            
            # Navigate back to the home page for the next test
            try:
                driver.get(BASE_URL)
                time.sleep(WAIT_TIME)
            except:
                print("Failed to navigate back to home page")
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_df = pd.DataFrame(results)
        results_file = f"results_{timestamp}.csv"
        results_df.to_csv(results_file, index=False)
        print(f"\nTesting complete! Results saved to {results_file}")
        
        # Statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r['Result'].startswith('P'))
        failed_tests = total_tests - passed_tests
        
        print(f"\nTest Summary:")
        print(f"  Total Tests: {total_tests}")
        print(f"  Passed Tests: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"  Failed Tests: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        return results_file
        
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        save_screenshot("fatal_error", error=True)
        return None
    finally:
        print("Tests completed")
        input("Press Enter to close the browser...")
        driver.quit()

if __name__ == "__main__":
    main()