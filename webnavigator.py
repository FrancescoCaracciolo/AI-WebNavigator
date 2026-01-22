from time import sleep
from urllib.parse import urljoin
from gi.repository import GLib
from .extensions import NewelleExtension
from .handlers import ExtraSettings
from .ui.widgets import BrowserWidget
from .utility.website_scraper import WebsiteScraper 
import threading 
import json
from .tools import create_io_tool

RELIABLE_PROMPT = """
**Role & Objective**  
You are an expert web-scraping and navigation agent. Your task is to extract accurate, verifiable information from webpages using the most efficient tools available.

**Navigation & Interaction Strategy**
1.  **Assess First:** Use `get_page_outline` or `get_page_info` to understand the page structure before deep scraping.
2.  **Efficient Extraction:** Use reduced content tools (`get_page_text`, `get_page_links`, `get_main_content`, `get_page_headings`) to minimize token usage whenever possible.
3.  **Targeted Search:** Use `search_page_text` if you are looking for specific keywords.
4.  **Interaction:** Use `click_element`, `fill_input`, and `submit_form` to navigate through interactive sites or fill out forms. Use `scroll_page` to see content beyond the initial viewport.
5.  **Data Extraction:** Use `get_tables` for structured data or `get_images` for visual information.

**Capabilities**  
- **Deep Navigation:** You can follow links, interact with buttons, and fill forms to locate answers across multiple pages.
- **Selective Extraction:** You can choose to get only text, links, headings, or main content to stay within token limits.

**Constraints**  
1.  **Source-Only Answers:** Base every answer strictly on content you've scraped. Do not use outside knowledge.
2.  **Reliability:** Only report clearly stated or supported information.
3.  **Traceability:** Reference the source URL or specific section where information was found.
4.  **Fallback:** If the current page lacks the answer, explore further using links or search forms.

**Workflow Example**  
1.  `get_page_outline()` to see if the page has what you need.
2.  `get_main_content()` or `search_page_text("query")` to find specific details.
3.  If answer is on another page, `click_element(selector)` or `openlink(url)`.
4.  Respond with clear citations.
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
    id = "webnavigator2"
    name = "Web Navigator 2"
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
        return [
            # Navigation tools
            create_io_tool("openlink", "Open a link and get full page content", self.openlink, tools_group="Web Navigation"),
            create_io_tool("click_element", "Click an element by CSS selector", 
                          lambda selector: str(self.click_element(selector)), tools_group="Web Navigation"),
            create_io_tool("fill_input", "Fill an input field (selector, value)", 
                          lambda selector, value: str(self.fill_input(selector, value)), tools_group="Web Navigation"),
            create_io_tool("submit_form", "Submit a form by CSS selector", 
                          lambda selector: str(self.submit_form(selector)), tools_group="Web Navigation"),
            create_io_tool("scroll_page", "Scroll the page (direction: up/down/top/bottom, amount: pixels for up/down)", 
                          lambda direction="down", amount=500: str(self.scroll_page(direction, amount)), tools_group="Web Navigation"),
            
            # Reduced content tools (low token usage)
            create_io_tool("get_page_text", "Get plain text content of the page (max_chars limits output)", 
                          lambda max_chars=2000: str(self.get_page_text(max_chars)), tools_group="Web Navigation"),
            create_io_tool("get_page_links", "Get all links on the page (max_links limits output)", 
                          lambda max_links=30: str(self.get_page_links(max_links)), tools_group="Web Navigation"),
            create_io_tool("get_page_headings", "Get all headings (h1-h6) from the page", 
                          lambda: str(self.get_page_headings()), tools_group="Web Navigation"),
            create_io_tool("get_page_outline", "Get a minimal structural outline of the page", 
                          lambda: str(self.get_page_outline()), tools_group="Web Navigation"),
            create_io_tool("get_interactive_elements", "Get buttons, inputs, and forms on the page", 
                          lambda: str(self.get_interactive_elements()), tools_group="Web Navigation"),
            create_io_tool("get_main_content", "Extract main content area only (max_chars limits output)", 
                          lambda max_chars=3000: str(self.get_main_content(max_chars)), tools_group="Web Navigation"),
            create_io_tool("search_page_text", "Search for text on the page and get surrounding context", 
                          lambda query: str(self.search_page_text(query)), tools_group="Web Navigation"),
            create_io_tool("get_tables", "Extract table data from the page", 
                          lambda: str(self.get_tables()), tools_group="Web Navigation"),
            create_io_tool("get_images", "Get images with alt text from the page", 
                          lambda max_images=20: str(self.get_images(max_images)), tools_group="Web Navigation"),
            
            # Page info tools
            create_io_tool("get_page_info", "Get basic page info (url, title, meta description)", 
                          lambda: str(self.get_page_info()), tools_group="Web Navigation"),
            create_io_tool("execute_js", "Execute custom JavaScript and return result", 
                          lambda js_code: str(self.execute_custom_js(js_code)), tools_group="Web Navigation"),
        ]

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
            parent = self.driver.get_display()
            if parent is not None:
                return
        self.tab = self.ui_controller.new_browser_tab(self.settings.get_string("initial-browser-page"), new=True)

        if self.tab is not None:
            self.driver = self.tab.get_child()


    def get_html_from_url(self, url):
        self.open_browser()
        self.driver.navigate_to(url) 
        html = self.driver.get_page_html_sync()
        return html 

    def run_javascript(self, script: str, callback):
        """
        Run JavaScript code in the browser and pass the output to the callback.
        Uses GLib.idle_add to ensure execution on the main GTK thread.

        Args:
            script (str): JavaScript code to execute
            callback (callable): Function to call with the result.
                                The callback will receive two parameters: (result, error)
                                where result is the JS result and error is None on success.
        """
        self.open_browser()

        def on_javascript_finished(webview, result, user_data):
            try:
                js_result = webview.evaluate_javascript_finish(result)
                if js_result:
                    result_value = js_result.to_string()
                    callback(result_value, None)
                else:
                    callback(None, "Failed to get JavaScript result")
            except Exception as e:
                callback(None, str(e))

        def schedule_on_main_thread():
            self.driver.webview.evaluate_javascript(
                script,
                -1,
                None,
                None,
                None,
                on_javascript_finished,
                None
            )
            return False  # Don't repeat

        GLib.idle_add(schedule_on_main_thread)

    def _escape_js_string(self, value: str) -> str:
        """Escape a string for safe insertion into JavaScript code"""
        return value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")

    def execute_javascript_sync(self, script: str, timeout: int = 10000) -> str:
        """
        Execute JavaScript code synchronously and return the result.
        Uses threading.Semaphore for synchronization.

        Args:
            script (str): JavaScript code to execute
            timeout (int): Timeout in milliseconds

        Returns:
            str: The result of the JavaScript execution
        """
        sem = threading.Semaphore(0)
        result_holder = {"value": ""}
        error_holder = {"value": None}

        def callback(res, err):
            result_holder["value"] = res if res else ""
            error_holder["value"] = err
            sem.release()

        self.run_javascript(script, callback)
        
        if not sem.acquire(timeout=timeout / 1000):
            error_holder["value"] = f"JavaScript execution timed out after {timeout}ms"

        if error_holder["value"]:
            raise Exception(error_holder["value"])
        return result_holder["value"]

    # ============ Navigation Tools ============

    def click_element(self, selector: str) -> dict:
        """Click an element by CSS selector"""
        escaped_selector = self._escape_js_string(selector)
        js_code = f"""
        (function() {{
            const el = document.querySelector('{escaped_selector}');
            if (el) {{
                const tagName = el.tagName;
                const href = el.href;
                const text = el.innerText?.substring(0, 50) || '';
                el.click();
                return JSON.stringify({{ success: true, clicked: tagName, href: href || null, text: text }});
            }}
            return JSON.stringify({{ success: false, error: 'Element not found: {escaped_selector}' }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fill_input(self, selector: str, value: str) -> dict:
        """Fill an input field with a value"""
        escaped_selector = self._escape_js_string(selector)
        escaped_value = self._escape_js_string(value)
        js_code = f"""
        (function() {{
            const el = document.querySelector('{escaped_selector}');
            if (el) {{
                el.value = '{escaped_value}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return JSON.stringify({{ success: true, filled: el.tagName, name: el.name || el.id }});
            }}
            return JSON.stringify({{ success: false, error: 'Element not found: {escaped_selector}' }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def submit_form(self, selector: str) -> dict:
        """Submit a form by selector"""
        escaped_selector = self._escape_js_string(selector)
        js_code = f"""
        (function() {{
            const form = document.querySelector('{escaped_selector}');
            if (form) {{
                form.submit();
                return JSON.stringify({{ success: true, submitted: true }});
            }}
            return JSON.stringify({{ success: false, error: 'Form not found: {escaped_selector}' }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception:
            return {"success": True, "submitted": True, "note": "Form submitted, page navigation likely occurred"}

    def scroll_page(self, direction: str = "down", amount: int = 500) -> dict:
        """Scroll the page in a direction"""
        js_code = f"""
        (function() {{
            const direction = '{direction}';
            const amount = {amount};
            let scrolled = false;
            
            if (direction === 'down') {{
                window.scrollBy(0, amount);
                scrolled = true;
            }} else if (direction === 'up') {{
                window.scrollBy(0, -amount);
                scrolled = true;
            }} else if (direction === 'top') {{
                window.scrollTo(0, 0);
                scrolled = true;
            }} else if (direction === 'bottom') {{
                window.scrollTo(0, document.body.scrollHeight);
                scrolled = true;
            }}
            
            return JSON.stringify({{
                success: scrolled,
                scrollY: window.scrollY,
                scrollHeight: document.body.scrollHeight,
                viewportHeight: window.innerHeight
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ============ Reduced Content Tools (Low Token Usage) ============

    def get_page_text(self, max_chars: int = 2000) -> dict:
        """Get plain text content of the page"""
        js_code = f"""
        (function() {{
            const maxChars = {max_chars};
            const body = document.body;
            
            // Remove script and style elements from consideration
            const clone = body.cloneNode(true);
            clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
            
            let text = clone.innerText.replace(/\\s+/g, ' ').trim();
            if (text.length > maxChars) {{
                text = text.substring(0, maxChars) + '...';
            }}
            
            return JSON.stringify({{
                url: window.location.href,
                title: document.title,
                text: text,
                totalLength: clone.innerText.length,
                truncated: clone.innerText.length > maxChars
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_page_links(self, max_links: int = 30) -> dict:
        """Get all links on the page"""
        js_code = f"""
        (function() {{
            const maxLinks = {max_links};
            const links = document.querySelectorAll('a[href]');
            const result = [];
            
            const seen = new Set();
            for (const a of links) {{
                if (result.length >= maxLinks) break;
                
                const href = a.href;
                const text = a.innerText.trim().substring(0, 80);
                
                // Skip empty links, anchors, and duplicates
                if (!text || href.startsWith('javascript:') || seen.has(href)) continue;
                seen.add(href);
                
                result.push({{ text, href }});
            }}
            
            return JSON.stringify({{
                url: window.location.href,
                totalLinks: links.length,
                links: result
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_page_headings(self) -> dict:
        """Get all headings from the page"""
        js_code = """
        (function() {
            const headings = [];
            document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
                const text = h.innerText.trim();
                if (text) {
                    headings.push({
                        level: h.tagName,
                        text: text.substring(0, 150)
                    });
                }
            });
            
            return JSON.stringify({
                url: window.location.href,
                title: document.title,
                headings: headings
            });
        })()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_page_outline(self) -> dict:
        """Get a minimal structural outline of the page"""
        js_code = """
        (function() {
            const outline = {
                url: window.location.href,
                title: document.title,
                metaDescription: document.querySelector('meta[name="description"]')?.content?.substring(0, 200) || '',
                structure: {
                    hasNav: !!document.querySelector('nav, [role="navigation"]'),
                    hasSearch: !!document.querySelector('input[type="search"], [role="search"]'),
                    hasMain: !!document.querySelector('main, [role="main"]'),
                    hasSidebar: !!document.querySelector('aside, [role="complementary"]'),
                    hasFooter: !!document.querySelector('footer')
                },
                counts: {
                    headings: document.querySelectorAll('h1, h2, h3, h4, h5, h6').length,
                    links: document.querySelectorAll('a[href]').length,
                    forms: document.querySelectorAll('form').length,
                    buttons: document.querySelectorAll('button, input[type="submit"]').length,
                    inputs: document.querySelectorAll('input, textarea, select').length,
                    images: document.querySelectorAll('img').length,
                    tables: document.querySelectorAll('table').length
                },
                firstHeading: document.querySelector('h1')?.innerText?.substring(0, 100) || ''
            };
            
            return JSON.stringify(outline);
        })()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_interactive_elements(self) -> dict:
        """Get buttons, inputs, and forms on the page"""
        js_code = """
        (function() {
            const result = {
                url: window.location.href,
                buttons: [],
                inputs: [],
                forms: []
            };
            
            // Buttons
            document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"]').forEach((btn, idx) => {
                if (idx < 15) {
                    result.buttons.push({
                        text: (btn.innerText || btn.value || btn.title || 'button').substring(0, 50),
                        id: btn.id || null,
                        class: btn.className?.substring(0, 50) || null,
                        type: btn.type || null
                    });
                }
            });
            
            // Inputs
            document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select').forEach((inp, idx) => {
                if (idx < 20) {
                    const label = inp.labels?.[0]?.innerText || inp.placeholder || inp.name || '';
                    result.inputs.push({
                        type: inp.type || inp.tagName.toLowerCase(),
                        name: inp.name || null,
                        id: inp.id || null,
                        label: label.substring(0, 50),
                        required: inp.required || false
                    });
                }
            });
            
            // Forms
            document.querySelectorAll('form').forEach((form, idx) => {
                if (idx < 10) {
                    result.forms.push({
                        id: form.id || null,
                        action: form.action || null,
                        method: form.method || 'get',
                        inputCount: form.querySelectorAll('input, textarea, select').length
                    });
                }
            });
            
            return JSON.stringify(result);
        })()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_main_content(self, max_chars: int = 3000) -> dict:
        """Extract main content area only"""
        js_code = f"""
        (function() {{
            const maxChars = {max_chars};
            
            // Try to find main content area
            const mainSelectors = ['main', 'article', '[role="main"]', '.content', '#content', '.post', '.article', '.entry-content'];
            let mainContent = null;
            
            for (const sel of mainSelectors) {{
                mainContent = document.querySelector(sel);
                if (mainContent) break;
            }}
            
            if (!mainContent) {{
                mainContent = document.body;
            }}
            
            // Clone and clean
            const clone = mainContent.cloneNode(true);
            clone.querySelectorAll('script, style, noscript, nav, header, footer, aside').forEach(el => el.remove());
            
            let text = clone.innerText.replace(/\\s+/g, ' ').trim();
            const totalLength = text.length;
            
            if (text.length > maxChars) {{
                text = text.substring(0, maxChars) + '...';
            }}
            
            return JSON.stringify({{
                url: window.location.href,
                title: document.title,
                content: text,
                totalLength: totalLength,
                truncated: totalLength > maxChars,
                selector: mainContent.tagName + (mainContent.id ? '#' + mainContent.id : '')
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def search_page_text(self, query: str) -> dict:
        """Search for text on the page and get surrounding context"""
        escaped_query = self._escape_js_string(query)
        js_code = f"""
        (function() {{
            const query = '{escaped_query}'.toLowerCase();
            const body = document.body.innerText;
            const bodyLower = body.toLowerCase();
            const results = [];
            
            let pos = 0;
            while (results.length < 10) {{
                const idx = bodyLower.indexOf(query, pos);
                if (idx === -1) break;
                
                // Get context around the match (100 chars before and after)
                const start = Math.max(0, idx - 100);
                const end = Math.min(body.length, idx + query.length + 100);
                const context = body.substring(start, end).replace(/\\s+/g, ' ');
                
                results.push({{
                    position: idx,
                    context: (start > 0 ? '...' : '') + context + (end < body.length ? '...' : '')
                }});
                
                pos = idx + query.length;
            }}
            
            return JSON.stringify({{
                url: window.location.href,
                query: '{escaped_query}',
                found: results.length > 0,
                matchCount: results.length,
                matches: results
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_tables(self) -> dict:
        """Extract table data from the page"""
        js_code = """
        (function() {
            const tables = [];
            
            document.querySelectorAll('table').forEach((table, tableIdx) => {
                if (tableIdx >= 5) return;
                
                const tableData = {
                    index: tableIdx,
                    id: table.id || null,
                    caption: table.querySelector('caption')?.innerText?.substring(0, 100) || null,
                    headers: [],
                    rows: []
                };
                
                // Get headers
                table.querySelectorAll('th').forEach(th => {
                    tableData.headers.push(th.innerText.trim().substring(0, 50));
                });
                
                // Get rows (limit to first 20)
                table.querySelectorAll('tr').forEach((tr, rowIdx) => {
                    if (rowIdx >= 20) return;
                    
                    const cells = [];
                    tr.querySelectorAll('td').forEach(td => {
                        cells.push(td.innerText.trim().substring(0, 100));
                    });
                    
                    if (cells.length > 0) {
                        tableData.rows.push(cells);
                    }
                });
                
                tables.push(tableData);
            });
            
            return JSON.stringify({
                url: window.location.href,
                tableCount: document.querySelectorAll('table').length,
                tables: tables
            });
        })()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_images(self, max_images: int = 20) -> dict:
        """Get images with alt text from the page"""
        js_code = f"""
        (function() {{
            const maxImages = {max_images};
            const images = [];
            
            document.querySelectorAll('img').forEach((img, idx) => {{
                if (idx >= maxImages) return;
                
                images.push({{
                    src: img.src,
                    alt: img.alt?.substring(0, 100) || '',
                    width: img.naturalWidth || img.width,
                    height: img.naturalHeight || img.height
                }});
            }});
            
            return JSON.stringify({{
                url: window.location.href,
                totalImages: document.querySelectorAll('img').length,
                images: images
            }});
        }})()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def get_page_info(self) -> dict:
        """Get basic page info"""
        js_code = """
        (function() {
            return JSON.stringify({
                url: window.location.href,
                title: document.title,
                metaDescription: document.querySelector('meta[name="description"]')?.content || '',
                metaKeywords: document.querySelector('meta[name="keywords"]')?.content || '',
                canonical: document.querySelector('link[rel="canonical"]')?.href || '',
                language: document.documentElement.lang || '',
                charset: document.characterSet,
                viewport: document.querySelector('meta[name="viewport"]')?.content || ''
            });
        })()
        """
        try:
            result = self.execute_javascript_sync(js_code)
            return json.loads(result)
        except Exception as e:
            return {"error": str(e)}

    def execute_custom_js(self, js_code: str) -> str:
        """Execute custom JavaScript and return the result"""
        try:
            return self.execute_javascript_sync(js_code)
        except Exception as e:
            return json.dumps({"error": str(e)})
