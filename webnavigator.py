from time import sleep
from urllib.parse import urljoin
from gi.repository import GLib
from .extensions import NewelleExtension
from .handlers import ExtraSettings
from .ui.widgets import BrowserWidget
from .utility.website_scraper import WebsiteScraper 
import threading 
from .tools import create_io_tool

RELIABLE_PROMPT = """
**Role & Objective**  
You are an expert web‑scraping agent. Your task is to extract accurate, verifiable information from a given webpage (and any subsequent pages you navigate to) without introducing unsupported assumptions.

**Capabilities**  
- **Open Links:** You can issue follow any hyperlink found on the current page.  
- **Deep Navigation:** You may recursively explore any “pertinent” links to locate answers.  

**Constraints**  
1. **Source‑Only Answers:** You must base every answer strictly on content you’ve scraped. Do **not** use outside knowledge or make inferences beyond the page’s data.  
2. **Reliability:** Only extract information that is clearly stated or supported by multiple on‑page references. Do **not** report rumors or unsubstantiated claims.  
3. **Traceability:** For each piece of information you present, reference the exact location (e.g. anchor text, paragraph number, or URL) where it was found.  
4. **Fallback Navigation:** If the current page lacks the answer, automatically follow any available “explore further” or related links until you either find the answer or exhaust relevant leads.

**Workflow**  
1. **Read & Analyze:** Parse the provided HTML/text.  
2. **Extract Candidate Answers:** Identify any direct statements or data relevant to the query.  
3. **Verify & Cite:** Confirm each fact against on‑page context and cite its source.  
4. **If Missing, Navigate:** Use 
```openlink
url
```
on pertinent links and repeat steps 1–3.  
5. **Respond:** Once you have a reliable answer, deliver it with clear citations. If no answer exists, state:  
   > “Answer not found in available sources.”  
"""

SUMMARY_PROMPT = """
You are provided with the following chat history and a simplified web page source code (each entry includes only a link and its accompanying text). Your task is to do the following:

1. Read the chat history to understand the context of the conversation.
2. Analyze the simplified web page source code to extract the most important points.
3. Generate a very brief summary of the web page (no more than one to two sentences).
4. Provide only a few (up to three) links from the source code that you believe will be most helpful for advancing the conversation.

Please ensure your output contains:
- A concise summary of the web page.
- A short list of relevant links (each link on its own line).

Do not include any additional commentary or details. Use only the information provided in the chat history and the web page source code.
 """

class WebNavigator (NewelleExtension):
    id = "webnavigator"
    name = "Web Navigator"
    driver : BrowserWidget | None = None
    old_pages = {}
    indexed_pages = []
    rag_index = None
    lasturl = ""
  
    def get_extra_settings(self) -> list:
        # Define extensions settings
        return [
           # ExtraSettings.ToggleSetting("headless", "Headless Mode", "Run in headless mode - don't show browser window", False),
            ExtraSettings.ToggleSetting("page_summary", "Generate Page Summary", "Generate a summary of old pages using the secondary LLM", False),
            ExtraSettings.ToggleSetting("remove_old_pages", "Remove Old Pages", "Remove old pages from the history", False),
            ExtraSettings.ToggleSetting("retrieve_information", "Use Document Analyzer", "Use the document analyzer to find information in old web pages", False),
        ]
 
    def get_additional_prompts(self) -> list:
        # Define additional prompts
        return [
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

    def openlink(self, url: str):
        return self.get_answer(url, "openlink")

    def get_tools(self) -> list:
        return [create_io_tool("openlink", "Open a link from the given page", self.openlink)]

    def get_replace_codeblocks_langs(self) -> list:
        # Give the codeblocks that are replaced by tool calls
        return []

    def get_context(self, query: str):
        if self.rag is None:
            return ""
        documents = []
        for url, content in self.old_pages.items():
            documents.append("text:" + content)
        if self.rag_index is None:
            self.rag_index = self.rag.build_index(documents, 1024)
            self.indexed_pages += documents
        else:
            diff = []
            for document in documents:
                if document not in self.indexed_pages:
                    diff.append(document)
            self.rag_index.insert(diff)
            self.indexed_pages += diff
        content = self.rag_index.query(query)
        return "\n".join(content)
    
    def preprocess_history(self, history: list, prompts: list) -> tuple[list, list]:
        # Preprocess the history before it is sent to the LLM
        query = ""
        for msg in history:
            if msg["User"] == "User":
                query = msg["Message"]
        # Find old web pages
        for msg in history.copy()[:-1]:
            if "Webnav Result: " in msg["Message"]:
                # Remove pages if the remove_old_pages setting is enabled
                if self.get_setting("remove_old_pages"):
                    msg["Message"] = "Old Web Page content"
                # Otherwise generate a page summery 
                elif self.get_setting("page_summary"):
                    txt = self.llm.generate_text(msg["Message"], history, [SUMMARY_PROMPT])
                    msg["Message"] = txt
                else:
                    msg["Message"] = ""
        # Use RAG to get relevant context from old web pages
        if self.get_setting("retrieve_information"):
            context = self.get_context(query)
            prompts.append("Context from previous websites:\n\n" + context)
        return history, prompts

    def get_answer(self, codeblock: str, lang: str) -> str | None:
        # Open the page and get its content
        # Create a semaphore to wait for the page content
        sem = threading.Semaphore(1)
        self.html = None
        def to_sync(codeblock):
            if self.driver is None:
                self.open_browser()
            if not codeblock.startswith("http"):
                codeblock = urljoin(self.lasturl, codeblock)
            self.lasturl = codeblock
            self.driver.navigate_to(codeblock)
            sem.release()
        sem.acquire()
        # Get the page content on the main UI thread
        GLib.idle_add(to_sync, codeblock)
        sem.acquire()
        sem.release()
        # Sleep a bit to be sure that loading started 
        sleep(1)
        # Wait for page loadaing
        self.driver.loading.acquire()
        self.driver.loading.release()
        # Get page HTMl
        self.html = self.driver.get_page_html_sync()
        # Clean the page content using Newelle's website scraper
        sc = WebsiteScraper(codeblock)
        sc.set_html(self.html)
        cleaned = sc.clean_html_to_markdown(self.html, include_links=True)
        self.old_pages[codeblock] = cleaned
        if lang == "openlink":
            return "Webnav Result: " + cleaned 
        return None

    def open_browser(self):
        if self.driver is not None:
            parent = self.tab.get_parent()
            if parent is not None:
                return
        self.tab = self.ui_controller.new_browser_tab(self.settings.get_string("initial-browser-page"), new=True)

        if self.tab is not None:
            self.driver = self.tab.get_child()


    def get_html_from_url(self, url):
        if self.driver is None:
            self.open_browser()
        self.driver.navigate_to(url) 
        html = self.driver.get_page_html_sync()
        return html 
