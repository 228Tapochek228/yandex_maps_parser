#!/usr/bin/env python3

# This crawler was developed on May 30, 2025, and by the time you, dear friend, use it, it may be outdated.

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    WebDriverException
)
from bs4 import BeautifulSoup
import argparse
import time
import csv
import os
import re
from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass


@dataclass
class BusinessInfo:
    name: Optional[str] = None
    phone: Optional[str] = None
    rating: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    rating_count: Optional[str] = None
    social_networks: Optional[str] = None
    yandex_link: Optional[str] = None


class Logger:
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

    FIELD_EMOJIS = {
        "name": "🏢",
        "category": "🏷️",
        "rating": "⭐",
        "rating_count": "🔢",
        "website": "🌐",
        "social_networks": "📱",
        "phone": "📞",
        "address": "📍"
    }

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def log(self, message: str, level: str = "info", emoji: Optional[str] = None) -> None:
        emoji = emoji or self.EMOJIS.get(level, "➡️")
        print(f"{emoji} [{level.upper()}] {message}")

    def debug(self, message: str) -> None:
        if self.debug_mode:
            self.log(message, "debug")

    def info(self, message: str) -> None:
        self.log(message, "info")

    def error(self, message: str) -> None:
        self.log(message, "error")

    def success(self, message: str) -> None:
        self.log(message, "success")


class YandexMapsCrawler:
    def __init__(self, headless: bool = False, debug: bool = False):
        self.logger = Logger(debug)
        self.driver = self._init_webdriver(headless)
        self.processed_elements: Set[str] = set()
        self.max_retries = 3
        self.wait_timeout = 10

    def _init_webdriver(self, headless: bool) -> webdriver.Firefox:
        options = webdriver.FirefoxOptions()
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        options.set_preference(
            "general.useragent.override",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        if headless:
            options.add_argument("--headless")
            self.logger.info("Running in headless mode")
        
        try:
            driver = webdriver.Firefox(options=options)
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            return driver
        except WebDriverException as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def _retry_on_failure(self, func, *args, **kwargs) -> Any:
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (StaleElementReferenceException, TimeoutException) as e:
                if attempt == self.max_retries - 1:
                    raise
                self.logger.debug(
                    f"Attempt {attempt + 1}/{self.max_retries} failed: {type(e).__name__}"
                )
                time.sleep(1)
        return None

    def perform_search(self, query: str) -> bool:
        try:
            search_input = self._retry_on_failure(
                WebDriverWait(self.driver, self.wait_timeout).until,
                EC.element_to_be_clickable((By.XPATH, "//input[@placeholder='Поиск и выбор мест']"))
            )
            
            if not search_input:
                return False
                
            search_input.clear()
            search_input.send_keys(query)
            search_input.send_keys(Keys.RETURN)
            self.logger.info(f"Search performed for: '{query}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Search error: {e}")
            return False

    def _is_collection_element(self, element) -> bool:
        try:
            if element.tag_name == "div" and "_type_collection" in element.get_attribute("class"):
                return True
                
            children = element.find_elements(By.XPATH, "./*")
            for child in children:
                if self._is_collection_element(child):
                    return True
                    
            return False
        except StaleElementReferenceException:
            self.logger.debug("Stale element while checking collection")
            return False

    def _click_element_safely(self, element) -> bool:
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                element
            )
            time.sleep(0.5)
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(element)).click()
            self.logger.debug("Click successful")
            return True
        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException) as e:
            self.logger.debug(f"Click failed: {type(e).__name__}")
            return False

    def _extract_link(self) -> str:
        try:
            soup = BeautifulSoup(self.driver.page_source, 'lxml')
            link = soup.select_one(".card-title-view__title-link")
            return f"https://yandex.ru{link.get('href')}" if link else None
        except Exception as e:
            self.logger.error(f"Failed to extract link: {e}")
            return None

    def _check_list_end(self) -> bool:
        try:
            end_marker = self.driver.find_element(
                By.XPATH, 
                "//span[contains(text(), 'Добавьте организацию или объект')]"
            )
            return end_marker is not None
        except NoSuchElementException:
            return False

    def process_search_results(self, check_interval: float = 1.0) -> List[str]:
        links: List[str] = []
        last_item_count = 0
        failed_attempts = 0
        max_failed_attempts = 10
        
        try:
            WebDriverWait(self.driver, self.wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.search-list-view__list"))
            )
        except TimeoutException:
            self.logger.error("Search results list not found")
            return links
            
        while failed_attempts < max_failed_attempts:
            try:
                current_items = self.driver.find_elements(
                    By.CSS_SELECTOR, "ul.search-list-view__list > li"
                )
                current_count = len(current_items)
                
                if current_count == 0:
                    time.sleep(check_interval)
                    failed_attempts += 1
                    continue
                    
                if current_count == last_item_count:
                    if self._check_list_end():
                        self.logger.info("Reached the end of the list")
                        break
                        
                    self._scroll_to_bottom()
                    failed_attempts += 1
                    time.sleep(check_interval)
                    continue
                    
                new_items = current_items[last_item_count:] if last_item_count > 0 else current_items
                links.extend(self._process_new_items(new_items))
                last_item_count = current_count
                failed_attempts = 0
                
            except Exception as e:
                self.logger.error(f"Error processing results: {type(e).__name__} - {e}")
                failed_attempts += 1
                
            time.sleep(check_interval)
            
        return links

    def _scroll_to_bottom(self) -> None:
        try:
            last_element = self.driver.find_elements(
                By.CSS_SELECTOR, "ul.search-list-view__list > li"
            )[-1]
            self.driver.execute_script(
                "arguments[0].scrollIntoView(); window.scrollBy(0, 500);",
                last_element
            )
        except Exception as e:
            self.logger.debug(f"Scroll failed: {e}")

    def _process_new_items(self, items: List) -> List[str]:
        new_links = []
        for index, item in enumerate(items, start=1):
            try:
                if self._is_collection_element(item):
                    self.logger.debug(f"Item {index} is collection - skipping")
                    continue
                    
                item_div = WebDriverWait(item, 5).until(
                    EC.presence_of_element_located((By.XPATH, "./div[1]"))
                )
                element_key = item_div.get_attribute("outerHTML")[:100]
                
                if element_key not in self.processed_elements:
                    self.logger.info(f"Processing item {index}/{len(items)}")
                    
                    if self._click_element_safely(item_div):
                        self.processed_elements.add(element_key)
                        time.sleep(1.5)
                        link = self._extract_link()
                        if link:
                            new_links.append(link)
                            self.driver.back()
                    else:
                        self.logger.debug("Failed to click item")
                        
            except Exception as e:
                self.logger.debug(f"Item processing error: {type(e).__name__}")
                continue
                
        return new_links
    
    def get_business_info(self, url: str) -> BusinessInfo:
        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for page to load
            
            soup = BeautifulSoup(self.driver.page_source, 'lxml')
            info = BusinessInfo(yandex_link=url)
            
            # Extract name
            name_elem = soup.select_one(".orgpage-header-view__header")
            info.name = name_elem.text.strip() if name_elem else None
            
            # Extract address
            address_elem = soup.select_one(".orgpage-header-view__address > div:nth-child(1)")
            info.address = address_elem.text.strip() if address_elem else None
            
            # Extract rating
            rating_elem = soup.select_one(".business-header-rating-view > div:nth-child(1) > div:nth-child(2) > span:nth-child(2)")
            info.rating = rating_elem.text.strip() if rating_elem else None
            
            # Extract rating count
            rating_count_elem = soup.select_one(".business-header-rating-view__text")
            if rating_count_elem:
                info.rating_count = rating_count_elem.text.strip().split(" ")[0]
            
            # Extract phone
            phone_elem = soup.select_one(".orgpage-phones-view__phone-number")
            info.phone = phone_elem.text.strip() if phone_elem else None
            
            # Extract social networks
            social_div = soup.select_one("div._view_normal:nth-child(4) > div:nth-child(1) > div:nth-child(1) > div:nth-child(2) > div:nth-child(1)")
            if social_div:
                social_links = [a.get("href") for a in social_div.find_all("a") if a.get("href")]
                info.social_networks = ",".join(social_links) if social_links else None
            
            # Extract website
            website_elem = soup.select_one(".business-urls-view__link")
            info.website = website_elem.get("href") if website_elem else None
            
            return info
            
        except Exception as e:
            self.logger.error(f"Failed to extract business info: {e}")
            return BusinessInfo(yandex_link=url)

    def save_to_csv(self, data: List[BusinessInfo], filename: str) -> None:
        try:
            file_exists = os.path.isfile(filename)
            
            with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'name', 'phone', 'rating', 'address', 
                    'website', 'rating_count', 'social_networks', 'yandex_link'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if not file_exists:
                    writer.writeheader()
                
                for business in data:
                    writer.writerow({
                        'name': business.name,
                        'phone': business.phone,
                        'rating': business.rating,
                        'address': business.address,
                        'website': business.website,
                        'rating_count': business.rating_count,
                        'social_networks': business.social_networks,
                        'yandex_link': business.yandex_link
                    })
                    
            self.logger.success(f"Data saved to {filename}")
            
        except Exception as e:
            self.logger.error(f"Failed to save data to CSV: {e}")

    def close(self) -> None:
        try:
            self.driver.quit()
            self.logger.info("WebDriver closed")
        except Exception as e:
            self.logger.error(f"Error closing WebDriver: {e}")

    @staticmethod
    def read_queries(file_path: str) -> List[str]:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return [line.strip() for line in file if line.strip()]
        except Exception as e:
            Logger().error(f"Failed to read queries: {e}")
            return []


def main():
    parser = argparse.ArgumentParser(description="Yandex maps parser")
    parser.add_argument("--queries", help="File with search queries", required=True)
    parser.add_argument("--output", help="Output CSV file (default: output.csv)", default="output.csv")
    parser.add_argument("--debug", help="Enable debug output", action="store_true")
    parser.add_argument("--headless", help="Run browser in headless mode", action="store_true")
    args = parser.parse_args()

    crawler = None
    try:
        crawler = YandexMapsCrawler(headless=args.headless, debug=args.debug)
        logger = crawler.logger

        logger.info("Starting Yandex Maps crawler")
        
        crawler.driver.maximize_window()
        crawler.driver.get("https://yandex.ru/maps/")
        time.sleep(2)

        queries = crawler.read_queries(args.queries)
        if not queries:
            logger.error("No queries found in input file")
            return
            
        logger.info(f"Found {len(queries)} queries to process")
        all_businesses = []
        
        for i, search_query in enumerate(queries, 1):
            logger.info(f"\nProcessing query {i}/{len(queries)}: '{search_query}'")
            
            if not crawler.perform_search(search_query):
                logger.error("Failed to perform search, skipping...")
                continue
                
            links = crawler.process_search_results()
            logger.info(f"Found {len(links)} businesses for query: '{search_query}'")
            
            for link in links:
                business_info = crawler.get_business_info(link)
                all_businesses.append(business_info)
                logger.debug(f"Processed: {business_info.name or 'Unknown'}")
                
            crawler.save_to_csv(all_businesses, args.output)
            logger.info(f"Finished processing query: '{search_query}'")

        logger.success("\nAll queries processed successfully!")
        logger.info(f"Total businesses collected: {len(all_businesses)}")

    except Exception as e:
        logger.error(f"Fatal error: {type(e).__name__} - {str(e)}")

    finally:
        if crawler:
            crawler.close()


if __name__ == "__main__":
    main()
