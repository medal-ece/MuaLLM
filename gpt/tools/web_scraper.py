import json
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# Save cookies to a JSON file
def save_cookies(driver, cookies_file):
    cookies = driver.get_cookies()
    with open(cookies_file, 'w') as f:
        json.dump(cookies, f)
    print("Cookies have been saved to ieee_cookies.json")


# Load cookies from a JSON file if it exists
def load_cookies(driver, cookies_file):
    if os.path.exists(cookies_file):
        with open(cookies_file, 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            if 'domain' not in cookie:
                cookie['domain'] = '.ieeexplore.ieee.org'
            driver.add_cookie(cookie)
        print("Cookies loaded successfully.")
        return True
    else:
        print("No cookies file found. Proceeding without cookies.")
        return False


# Open the browser, load cookies if available, and prompt for login if necessary
def initialize_browser_with_cookies(download_path):
    # Ensure the download directory exists
    if not os.path.exists(download_path):
        os.makedirs(download_path)
        print(f"Created download directory: {download_path}")
    else:
        print(f"Download directory already exists: {download_path}")

    options = Options()
    options.add_experimental_option("prefs", {
        "download.default_directory": download_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True
    })

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    # Navigate to IEEE Xplore to initialize the session
    driver.get("https://ieeexplore.ieee.org")


    # Load cookies if they exist
    cookies_loaded = load_cookies(driver, 'ieee_cookies.json')
    driver.refresh()  # Refresh the page to apply cookies

    # Prompt the user to log in if needed
    input("If not already logged in, log in manually in the browser and then press Enter here.")

    save_cookies(driver, 'ieee_cookies.json')  # Update cookies
    print("Updated login cookies")

    return driver

#function to enter search
def perform_search(driver, search_query):
    try:
        print("Looking for search bar...")
        # Updated selector to match the actual element
        search_bar = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR, 
                "input.Typeahead-input[type='search'][aria-label='main']"
            ))
        )
        
        print("Found search bar, entering query...")
        search_bar.clear()
        search_bar.send_keys(search_query)
        search_bar.send_keys(u'\ue007')  # Press Enter
        print(f"Searching for '{search_query}'")
        
        # Give the page time to load results
        time.sleep(2)
        
    except Exception as e:
        print(f"Error during search: {e}")


# Helper function to click using JavaScript
def javascript_click(driver, element, links):
    #scroll when scraping links
    if links:
        driver.execute_script("arguments[0].scrollIntoView(true);", element)  # Scroll into view
        time.sleep(0.5)  # Allow time to stabilize
    driver.execute_script("arguments[0].click();", element)


# Scrape links from search results for a specified number of pages
def scrape_links(driver, pages_to_scrape, max_retries=3):
    print(f"Starting to scrape search result links for {pages_to_scrape} pages...")
    links = []
    current_page = 1  # Start from the first page

    while current_page <= pages_to_scrape:
        print(f"Scraping page {current_page}...")
        retries = 0

        while retries < max_retries:
            try:
                # Wait until search result links are visible
                WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.XPATH, "//i[contains(@class, 'fa-file-pdf')]/parent::a"))
                )
                result_blocks = driver.find_elements(By.XPATH, "//i[contains(@class, 'fa-file-pdf')]/parent::a")

                # Extract and clean the href attribute
                if result_blocks:
                    for result in result_blocks:
                        href = result.get_attribute('href')
                        if href:
                            # Ensure we only scrape if the link is relative
                            if href.startswith("/"):
                                href = "https://ieeexplore.ieee.org" + href
                            if href not in links:  # Avoid duplicates
                                links.append(href)

                    print(f"Page {current_page} complete. Total links collected so far: {len(links)}.")
                    break  # Exit the retry loop if successful

                else:
                    raise Exception("No links found on page.")

            except Exception as e:
                print(f"Error on page {current_page}: {e}")
                retries += 1
                if retries < max_retries:
                    print(f"Retrying page {current_page} ({retries}/{max_retries})...")
                    driver.refresh()
                    time.sleep(2)  # Wait for the page to reload
                else:
                    print(f"Skipping page {current_page} after {max_retries} retries.")
                    break  # Move to the next page if max retries are exceeded

        # Stop clicking the "Next" arrow if we've reached the specified number of pages
        if current_page >= pages_to_scrape:
            print(f"Reached the desired number of pages")
            break

        # Move to the next page by clicking on the next arrow button
        try:
            print("Clicking 'Next' arrow to load the next page...")
            next_arrow_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'stats-Pagination_arrow_next')]"))
            )

            # Check if the next button is enabled stop if not
            if not next_arrow_button.is_enabled():
                print("No further pages. Reached the end of pages")
                break


            javascript_click(driver, next_arrow_button, links=True)  # Click using JavaScript
            print("Clicked 'Next' arrow successfully.")


            current_page += 1
        except Exception as e:
            print("Unable to locate or click the next arrow button. Stopping.")
            break  # Stop if no more pages

    print(f"Scraping complete. Total links scraped: {len(links)}.")
    return links

def download_pdfs(driver, links):
    print(f"Starting download of {len(links)} PDFs...")

    total_downloaded = 0

    for idx, link in enumerate(links, start=1):

        driver.get(link)

        try:
            #locate the iframe containing the "open" button.
            iframe = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'stampPDF')]"))
            )
            driver.switch_to.frame(iframe)

            #click the open button
            open_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "open-button"))
            )
            # Click the button using JavaScript
            javascript_click(driver, open_button, links=False)

            print(f"({idx}/{len(links)}) PDF downloading...")
            total_downloaded += 1
        except Exception as e:
            print(f"Failed to download PDF from {link}: {e}")
        finally:
            driver.switch_to.default_content()  # Return to main context

    print(f"Download complete. Total PDFs downloaded: {total_downloaded}.")


def main():
    download_folder = os.path.join(os.getcwd(), "IEEE_pdfs")
    # Initialize the browser
    driver = initialize_browser_with_cookies(download_folder)

    # Navigate to the search page and get user input
    driver.get("https://ieeexplore.ieee.org/search/searchresult.jsp")

    search_query = input("Enter your search query: ")
    perform_search(driver, search_query)  # Perform the search

    # Ask for the number of pages to scrape
    pages_to_scrape = int(input("Enter the number of pages to scrape: "))

    # Scrape links from the specified number of pages
    links = scrape_links(driver, pages_to_scrape)
    if links:
        with open("output.txt", "w") as f:
            for link in links:
                f.write(f"{link}\n")
        print("Links written to output.txt")
    else:
        print("No links found.")

    # Prompt user to confirm downloads
    print(f"{len(links)} PDFs will be downloaded.")
    input("Press Enter to start downloading...")

    download_pdfs(driver, links)

    print("Scraping complete. Closing the browser.")
    driver.quit()


if __name__ == '__main__':
    main()