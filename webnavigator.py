from gi.repository import Gtk
from .extra import find_module, install_module
from .extensions import NewelleExtension
from threading import Thread
import os

RELIABLE_PROMPT = """
You are a skilled expert web scraper. 
You are able find a lot of hidden information, hidden but reliable.
You can't deliver unreliable information.
Don't use knowledge not in the page to answer the question.

You are given the content of a webpage.
Stick your research field to the links you find in the page.
You are able to navigate all the pertinent links in the page. 
If a link to explore further is available, show it.

If you can't find the answer in the current page, visit another one.
"""

class WebNavigator (NewelleExtension):
    id = "webnavigator"
    name = "Web Navigator"

    def get_extra_settings(self) -> list:
        return [
            {
                "key": "headless",
                "type": "toggle",
                "title": "Headless Mode",
                "description": "Run in headless mode - don't show browser window",
                "default": False
            }
        ]
    def install(self):
        if not find_module("selenium"):
            install_module("selenium", self.pip_path)
        if not find_module("bs4"):
            install_module("beautifulsoup4", self.pip_path)
        if not find_module("markdownify"):
            install_module("markdownify", self.pip_path)
    
    def get_additional_prompts(self) -> list:
        return [
            {
                "key": "open_browser",
                "setting_name": "open_browser",
                "title": "Open Web Browser",
                "description": "Open web browser",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Use \n```web\nopen\n```\n to open a web browser"
            },
            {
                "key": "open_link",
                "setting_name": "open_link",
                "title": "Open Link",
                "description": "Open a link from the given page",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": "Use \n```website\nlink\n```\n to open a website at the given link. When opening a website, don't write anything else."
            },
            {
                "key": "information_reliability_prompt",
                "setting_name": "information_reliability_prompt",
                "title": "Enforce the LLM to provide reliable information",
                "description": "Enforce the LLM to provide reliable information, supposed to be used with web navigator.",
                "editable": True,
                "show_in_settings": True,
                "default": True,
                "text": RELIABLE_PROMPT
            }
        ]

    def get_replace_codeblocks_langs(self) -> list:
        return ["web", "website"]
    def get_gtk_widget(self, codeblock: str, lang: str) -> Gtk.Widget | None:
        if lang == "web":
            Thread(target=self.open_browser).start()
            return Gtk.Spinner(spinning=True)
        return None

    def get_answer(self, codeblock: str, lang: str) -> str | None:
        if lang == "website":
            return self.clean_html_to_markdown(self.get_html_from_url(codeblock))
        return None

    def open_browser(self):

        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        # Set up Chrome options
        chrome_options = Options()
        if self.get_setting("headless"):
            chrome_options.add_argument("--headless")  # Uncomment this line if you want to run in headless mode
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        if os.environ.get("WAYLAND_DISPLAY"):
            chrome_options.add_argument("--ozone-platform=wayland")

        service = Service()  # Update this path to where your chromedriver is located
        driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver = driver


    def get_html_from_url(self, url):
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        self.driver.get(url)
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        return self.driver.page_source 
    
    def clean_html_to_markdown(self, html_content):
        from bs4 import BeautifulSoup
        from markdownify import markdownify as md
        # Parse the HTML content
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove images
        for img in soup.find_all('img'):
            img.decompose()
        
        # Remove style and script tags
        for tag in soup(['style', 'script']):
            tag.decompose()
        
        # Remove all tags except links, paragraphs, lists, bold, italic
        for tag in soup.find_all(True):
            if tag.name not in ['a', 'p', 'ul', 'ol', 'li', 'b', 'strong', 'i', 'em']:
                tag.unwrap()
        
        # Convert the cleaned HTML to Markdown
        markdown_content = md(str(soup))
        
        # Extract links and format them as a list
        links = []
        for a_tag in soup.find_all('a', href=True):
            link_text = a_tag.get_text(strip=True)
            link_url = a_tag['href']
            links.append(f"- [{link_text}]({link_url})")
        
        # Join the links into a single string
        links_list = "\n".join(links)
        
        # Combine the Markdown content and the links list
        final_content = f"{markdown_content}\n\n## Links\n{links_list}"
        
        return final_content
