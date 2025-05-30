#!/usr/bin/env python3
# This crawler was developed on May 30, 2025, and by the time you, dear friend, use it, it may be outdated.

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException, ElementClickInterceptedException, WebDriverException
from bs4 import BeautifulSoup
from typing import Dict, Optional
import argparse
import time
import csv
import os

# Эмоджи для вывода
EMOJIS = {
    "info": "ℹ️",
    "error": "❌",
    "success": "✅",
    "debug": "🐛",
    "search": "🔍",
    "data": "📊",
    "file": "📁",
    "web": "🌐",
    "warning": "⚠️"
}

def log_debug(message):
    if args.debug:
        print(f"{EMOJIS['debug']} [DEBUG] {message}")

def log_info(message):
    print(f"{EMOJIS['info']} [INFO] {message}")

def log_critical(message):
    print(f"{EMOJIS['error']} [CRITICAL] {message}")

def log_success(message):
    print(f"{EMOJIS['success']} [SUCCESS] {message}")

def print_data(data):
    """Красивый вывод данных в консоль с эмоджи"""
    if not data:
        log_info("No data to display")
        return
        
    log_info("Extracted data:")
    max_key_length = max(len(key) for key in data.keys())
    
    # Специальные эмоджи для разных полей
    field_emojis = {
        "name": "🏢",
        "category": "🏷️",
        "rating": "⭐",
        "rating_count": "🔢",
        "website": "🌐",
        "vk_group": "📱",
        "phone": "📞",
        "address": "📍"
    }
    
    for key, value in data.items():
        if value is None:
            value = "N/A"
        emoji = field_emojis.get(key, "➡️")
        print(f"  {emoji} {key.ljust(max_key_length)} : {value}")

def init_webdriver():
    options = webdriver.FirefoxOptions()
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("general.useragent.override",
                         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    if args.headless:
        options.add_argument("--headless")
        log_info("Running in headless mode")
    
    driver = webdriver.Firefox(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def perform_search(query, driver, max_attempts=4):
    attempt = 0
    while attempt < max_attempts:
        try:
            search_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Поиск и выбор мест']"))
            )
            search_input.clear()
            search_input.send_keys(query)
            search_input.send_keys(Keys.RETURN)
            log_info(f"{EMOJIS['search']} Search performed for: '{query}'")
            return True
            
        except StaleElementReferenceException:
            log_debug(f"Attempt {attempt + 1}/{max_attempts}: stale element, retrying")
            attempt += 1
            time.sleep(1)
            
        except Exception as e:
            log_debug(f"Search error: {e}")
            break
    return False

def is_collection_element(element):
    try:
        if element.tag_name == "div" and "_type_collection" in element.get_attribute("class"):
            return True
            
        children = element.find_elements(By.XPATH, "./*")
        for child in children:
            if is_collection_element(child):
                return True
                
        return False
    except StaleElementReferenceException:
        log_debug("Stale element while checking collection")
        return False

def click_element_safely(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", element)
        time.sleep(0.3)
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(element)).click()
        log_debug("Click successful")
        return True
    except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException) as e:
        log_debug(f"Click failed: {type(e).__name__}")
        return False

def extract_data(soup: BeautifulSoup) -> Dict[str, Optional[str]]:
    def get_text_or_none(element) -> Optional[str]:
        return element.get_text(strip=True) if element else None
    
    def get_attr_or_none(element, attr: str) -> Optional[str]:
        return element.get(attr) if element else None
    
    result = {
        "name": None,
        "category": None,
        "rating": None,
        "rating_count": None,
        "website": None,
        "vk_group": None,
        "phone": None,
        "address": None
    }
    
    name_tag = soup.find('h1', class_='card-title-view__title')
    result['name'] = get_text_or_none(name_tag)
    
    category_tag = soup.find('a', class_='business-categories-view__category')
    if category_tag:
        result['category'] = get_text_or_none(category_tag)
    
    rating_tag = soup.find('span', class_='business-rating-badge-view__rating-text')
    result['rating'] = get_text_or_none(rating_tag)
    
    rating_count_tag = soup.find('div', class_='business-header-rating-view__text')
    if rating_count_tag:
        rating_text = rating_count_tag.get_text(strip=True)
        result['rating_count'] = rating_text.split()[0] if rating_text else None
    
    website_tag = soup.find('a', class_='business-urls-view__link', itemprop='url')
    result['website'] = get_attr_or_none(website_tag, 'href')
    
    vk_tag = soup.find('a', class_='business-contacts-view__social-button', href=lambda x: x and 'vk.com' in x)
    result['vk_group'] = get_attr_or_none(vk_tag, 'href')
    
    phone_tag = soup.find('span', itemprop='telephone')
    result['phone'] = get_text_or_none(phone_tag)
    
    address_tag = soup.find('div', class_='business-contacts-view__address-link')
    result['address'] = get_text_or_none(address_tag)
    
    return result

def check_list_end(driver):
    try:
        parent_div = driver.find_element(By.CSS_SELECTOR, "div.add-business-view")
        
        spans = parent_div.find_elements(By.CSS_SELECTOR, "span")
        if len(spans) < 5:
            return False
        
        if spans[0].text.strip() != "Добавьте":
            return False
        
        org_div = spans[1].find_elements(
            By.CSS_SELECTOR, 
            'div.add-business-view__link[aria-label="организацию"][role="link"]'
        )
        if not org_div or org_div[0].text.strip() != "организацию":
            return False
        
        if spans[2].text.strip() != "или":
            return False
        
        obj_link = spans[3].find_elements(By.CSS_SELECTOR, "a.add-business-view__link")
        if not obj_link or obj_link[0].text.strip() != "объект":
            return False
        
        if ", если не нашли их на карте." not in spans[4].text.strip():
            return False
        
        return True
    
    except NoSuchElementException:
        return False

def save_to_csv(data, filename, mode='a'):
    """Улучшенная функция сохранения в CSV с проверкой существования файла"""
    headers = ['name', 'category', 'rating', 'rating_count', 'website', 'vk_group', 'phone', 'address']
    
    file_exists = os.path.isfile(filename)
    
    try:
        with open(filename, mode=mode, newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            
            # Записываем заголовок только если файл новый или режим перезаписи
            if not file_exists or mode == 'w':
                writer.writeheader()
            
            writer.writerow(data)
        
        log_success(f"{EMOJIS['file']} Data saved to {filename}")
        return True
    except Exception as e:
        log_critical(f"Failed to save data: {e}")
        return False

def process_search_results(driver, check_interval=1):
    last_item_count = 0
    processed_elements = set()
    attempt = 0
    failed_attempts = 0  # Счетчик неудачных попыток получить новые элементы
    max_failed_attempts = 10  # Максимальное количество неудачных попыток
    
    while True:
        attempt += 1
        log_debug(f"\nProcessing attempt {attempt}")
        
        try:
            list_container = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.search-list-view__list"))
            )
            
            current_items = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located(
                    (By.CSS_SELECTOR, "ul.search-list-view__list > li")))
            
            current_count = len(current_items)
            log_debug(f"Items found: {current_count} (previous: {last_item_count})")
            
            if current_count == 0:
                log_debug("Empty list, waiting...")
                time.sleep(check_interval)
                failed_attempts += 1
                continue
                
            if current_count == last_item_count:
                try:
                    last_element = current_items[-1]
                    driver.execute_script(
                        "arguments[0].scrollIntoView();"
                        "window.scrollBy(0, 500);",
                        last_element
                    )
                    log_debug("Scrolled down 500px from last element")
                except Exception as e:
                    log_debug(f"Scroll failed: {e}")
                
                time.sleep(check_interval)
                
                # Проверка конца списка
                if check_list_end(driver):
                    log_info("Reached the end of the list")
                    return
                
                # Проверка количества неудачных попыток
                failed_attempts += 1
                if failed_attempts >= max_failed_attempts:
                    log_info(f"Reached maximum failed attempts ({max_failed_attempts}), stopping")
                    return
                else:
                    log_debug(f"Failed attempts: {failed_attempts}/{max_failed_attempts}")
                    continue
            else:
                # Сброс счетчика неудачных попыток при успешном получении новых элементов
                failed_attempts = 0
                
            new_items = current_items[last_item_count:] if last_item_count > 0 else current_items
            log_debug(f"New items to process: {len(new_items)}")
            
            for index, item in enumerate(new_items, start=1):
                try:
                    if is_collection_element(item):
                        log_debug(f"Item {index} is collection - skipping")
                        continue
                        
                    item_div = WebDriverWait(item, 5).until(
                        EC.presence_of_element_located((By.XPATH, "./div[1]")))
                    
                    element_key = item_div.get_attribute("outerHTML")[:100]
                    
                    if element_key not in processed_elements:
                        log_info(f"{EMOJIS['data']} Processing item {index}/{len(new_items)}")
                        
                        if click_element_safely(driver, item_div):
                            processed_elements.add(element_key)
                            log_debug("Click successful")
                            time.sleep(1)
                            data = extract_data(BeautifulSoup(driver.page_source, 'lxml'))
                            if data:
                                print_data(data)
                                save_to_csv(data, args.output or "output.csv", 'a')
                            driver.execute_script("window.history.back();")
                            time.sleep(1)
                        else:
                            log_debug("Failed to click item")
                            
                except (StaleElementReferenceException, TimeoutException, NoSuchElementException) as e:
                    log_debug(f"Item processing error: {type(e).__name__}")
                    continue
                    
            last_item_count = current_count
            
        except Exception as e:
            log_critical(f"{type(e).__name__} - {str(e)}")
            break
            
        time.sleep(check_interval)

def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return [line.strip() for line in file if line.strip()]
    except Exception as e:
        log_critical(f"{type(e).__name__} - {str(e)}")
        return []

def main():
    global args
    parser = argparse.ArgumentParser(description="Yandex maps parser")
    parser.add_argument("--queries", help="File with search queries", required=True)
    parser.add_argument("--output", help="Output CSV file (default: output.csv)", default="output.csv")
    parser.add_argument("--debug", help="Enable debug output", action="store_true")
    parser.add_argument("--headless", help="Run browser in headless mode", action="store_true")
    args = parser.parse_args()

    log_info(f"{EMOJIS['web']} Starting Yandex Maps crawler")
    driver = init_webdriver()
    driver.fullscreen_window()
    
    try:
        queries = read_file(args.queries)
        if not queries:
            log_critical("No queries found in input file")
            return
            
        log_info(f"Found {len(queries)} queries to process")
        
        for i, search_query in enumerate(queries, 1):
            log_info(f"\n{EMOJIS['search']} Processing query {i}/{len(queries)}: '{search_query}'")
            driver.get("https://yandex.ru/maps/")
            time.sleep(2)        

            if not perform_search(search_query, driver):
                log_critical("Failed to perform search, skipping...")
                continue
                
            process_search_results(driver)
            log_info(f"Finished processing query: '{search_query}'")

        log_success(f"\n{EMOJIS['success']} All queries processed successfully!")

    except WebDriverException as e:
        log_critical(f"WebDriver error: {e}")

    except Exception as e:
        log_critical(f"{type(e).__name__} - {str(e)}")

    finally:
        driver.quit()
        log_info(f"{EMOJIS['web']} WebDriver closed")

if __name__ == "__main__":
    main()
