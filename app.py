from flask import Flask, render_template, request, jsonify, session, redirect, url_for
try:
    from flask_session import Session
except ImportError:
    # Fallback for different flask-session versions
    import flask_session
    Session = getattr(flask_session, 'Session', None)
    if Session is None:
        # If Session is not available, we'll use a simple in-memory session
        class Session:
            def __init__(self, app):
                pass
import tempfile
import os
from typing import List, Dict
import pandas as pd
import PyPDF2
from docx import Document
import io
import google.generativeai as genai
import requests
from msal import ConfidentialClientApplication
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'fallback-secret-key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = False
Session(app)

# Azure AD Configuration
CLIENT_ID = os.getenv('AZURE_CLIENT_ID')
CLIENT_SECRET = os.getenv('AZURE_CLIENT_SECRET')
TENANT_ID = os.getenv('AZURE_TENANT_ID')
REDIRECT_URI = os.getenv('AZURE_REDIRECT_URI', 'http://localhost:5000/auth/callback')

# CORRECT SCOPES FOR ONEDRIVE ACCESS
SCOPES = [
    "https://graph.microsoft.com/Files.Read",
    "https://graph.microsoft.com/Files.Read.All", 
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Sites.Read.All"
]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

# Gemini Configuration
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class OneDriveGeminiAssistant:
    def __init__(self, access_token):
        self.access_token = access_token
        self.genai = self.initialize_gemini()
        self.file_cache = {}  # Cache for downloaded file contents
        self.cache_max_size = 50  # Maximum number of files to cache
        print(f"✅ Assistant initialized with access token: {bool(access_token)}")
    
    def initialize_gemini(self):
        """Initialize Gemini with correct configuration"""
        try:
            if not GEMINI_API_KEY:
                print("❌ No Gemini API key found")
                return None
                
            # Configure Gemini
            genai.configure(api_key=GEMINI_API_KEY)
            
            # Try different model names (updated for current API)
            model_names_to_try = [
                "gemini-2.5-flash",
                "models/gemini-2.5-flash",
                "models/gemini-2.5-pro"
            ]
            
            successful_model = None
            for model_name in model_names_to_try:
                try:
                    print(f"🔄 Trying model: {model_name}")
                    model = genai.GenerativeModel(model_name)
                    # Test with a simple prompt
                    response = model.generate_content("Hello")
                    if response and response.text:
                        successful_model = model_name
                        print(f"✅ Successfully initialized: {model_name}")
                        break
                    else:
                        print(f"⚠️ Model {model_name} responded but with no text")
                except Exception as e:
                    print(f"❌ Failed with {model_name}: {e}")
                    continue
            
            if successful_model:
                return genai.GenerativeModel(successful_model)
            else:
                print("❌ All model attempts failed")
                print("💡 Check your API key at: https://aistudio.google.com/app/apikey")
                return None
                
        except Exception as e:
            print(f"❌ Gemini configuration error: {e}")
            return None

    def make_graph_api_call(self, endpoint):
        """Make Microsoft Graph API calls"""
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            url = f"https://graph.microsoft.com/v1.0{endpoint}"
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print(f"❌ Permission denied for: {endpoint}")
                return None
            else:
                print(f"❌ API call failed ({response.status_code}): {endpoint}")
                return None
                
        except Exception as e:
            print(f"❌ API call error: {e}")
            return None

    def test_connection(self):
        """Test if we can access OneDrive"""
        try:
            print("🔍 Testing OneDrive connection...")
            
            # Test 1: Can we get user info?
            user_info = self.make_graph_api_call('/me')
            if not user_info:
                return "❌ Cannot get user information"
            
            user_name = user_info.get('displayName', 'Unknown')
            print(f"✅ User: {user_name}")
            
            # Test 2: Can we access OneDrive?
            drive_info = self.make_graph_api_call('/me/drive')
            if not drive_info:
                return "❌ Cannot access OneDrive - check Files.Read permissions"
            
            print(f"✅ OneDrive Type: {drive_info.get('driveType', 'Unknown')}")
            
            # Test 3: Can we list root items?
            root_items = self.make_graph_api_call('/me/drive/root/children')
            if not root_items:
                return "❌ Cannot list root items"
            
            items = root_items.get('value', [])
            print(f"✅ Found {len(items)} items in root directory")
            
            return f"✅ Connection successful! Found {len(items)} items in OneDrive root"
            
        except Exception as e:
            return f"❌ Connection test error: {str(e)}"

    def get_directory_structure(self, folder_path="/"):
        """Get complete directory structure from OneDrive"""
        try:
            print(f"📁 Getting directory structure from: {folder_path}")
            
            if folder_path == "/":
                endpoint = '/me/drive/root/children'
            else:
                # Remove leading slash for API call
                folder_path_clean = folder_path.lstrip('/')
                endpoint = f"/me/drive/root:/{folder_path_clean}:/children"
            
            items_data = self.make_graph_api_call(endpoint)
            if not items_data:
                print(f"❌ No data returned for: {folder_path}")
                return []
            
            items = items_data.get('value', [])
            print(f"✅ Found {len(items)} items in {folder_path}")
            
            structure = []
            for item in items:
                item_name = item.get('name', 'Unknown')
                item_type = 'folder' if 'folder' in item else 'file'
                
                item_info = {
                    'name': item_name,
                    'type': item_type,
                    'id': item.get('id'),
                    'size': item.get('size', 0),
                    'last_modified': item.get('lastModifiedDateTime'),
                    'path': folder_path,
                    'web_url': item.get('webUrl')
                }
                
                # If it's a folder, get its contents recursively
                if item_type == 'folder':
                    subfolder_path = f"{folder_path.rstrip('/')}/{item_name}" if folder_path != "/" else f"/{item_name}"
                    item_info['children'] = self.get_directory_structure(subfolder_path)
                else:
                    file_ext = item_name.lower().split('.')[-1] if '.' in item_name else 'unknown'
                    item_info['extension'] = file_ext
                
                structure.append(item_info)
            
            return structure
            
        except Exception as e:
            print(f"❌ Error getting directory structure for {folder_path}: {e}")
            return []

    def get_all_files_flat(self):
        """Get all files in a flat list recursively from all folders"""
        try:
            print("🔍 Getting all files from OneDrive recursively...")
            
            # Try different approaches to get files
            files = []
            
            # Method 1: Try search endpoint (most comprehensive)
            try:
                print("Trying search endpoint...")
                endpoint = "/me/drive/root/search(q='')"
                search_data = self.make_graph_api_call(endpoint)
                
                if search_data and 'value' in search_data:
                    items = search_data.get('value', [])
                    print(f"Search found {len(items)} items")
                    
                    for item in items:
                        if 'folder' not in item:  # It's a file
                            item_name = item.get('name', 'Unknown')
                            file_ext = item_name.lower().split('.')[-1] if '.' in item_name else 'unknown'
                            
                            file_data = {
                                'name': item_name,
                                'id': item.get('id'),
                                'type': file_ext,
                                'size': item.get('size', 0),
                                'last_modified': item.get('lastModifiedDateTime'),
                                'path': item.get('parentReference', {}).get('path', '/'),
                                'web_url': item.get('webUrl')
                            }
                            files.append(file_data)
                    
                    if files:
                        print(f"Search method found {len(files)} files")
                        return files
                else:
                    print("Search endpoint returned no data")
            except Exception as e:
                print(f"Search method failed: {e}")
            
            # Method 2: Recursive traversal of all folders
            try:
                print("📡 Trying recursive folder traversal...")
                files = self.get_files_recursively("/")
                if files:
                    print(f"Recursive method found {len(files)} files")
                    return files
            except Exception as e:
                print(f"Recursive method failed: {e}")
            
            # Method 3: Try getting root children
            try:
                print("Trying root children endpoint...")
                endpoint = "/me/drive/root/children"
                root_data = self.make_graph_api_call(endpoint)
                
                if root_data and 'value' in root_data:
                    items = root_data.get('value', [])
                    print(f"Root children found {len(items)} items")
                    
                    for item in items:
                        if 'folder' not in item:  # It's a file
                            item_name = item.get('name', 'Unknown')
                            file_ext = item_name.lower().split('.')[-1] if '.' in item_name else 'unknown'
                            
                            file_data = {
                                'name': item_name,
                                'id': item.get('id'),
                                'type': file_ext,
                                'size': item.get('size', 0),
                                'last_modified': item.get('lastModifiedDateTime'),
                                'path': item.get('parentReference', {}).get('path', '/'),
                                'web_url': item.get('webUrl')
                            }
                            files.append(file_data)
                    
                    if files:
                        print(f"Root children method found {len(files)} files")
                        return files
                else:
                    print("Root children endpoint returned no data")
            except Exception as e:
                print(f"Root children method failed: {e}")
            
            # Method 4: Try getting drive info first
            try:
                print("Checking drive access...")
                drive_info = self.make_graph_api_call("/me/drive")
                if drive_info:
                    print(f"Drive access confirmed: {drive_info.get('driveType', 'Unknown')}")
                else:
                    print("❌ Cannot access drive")
            except Exception as e:
                print(f"Drive access failed: {e}")
            
            print(f"No files found using any method")
            return []
            
        except Exception as e:
            print(f"Error getting all files: {e}")
            return []

    def get_files_recursively(self, folder_path="/", max_depth=5, current_depth=0):
        """Recursively get all files from folders"""
        try:
            if current_depth >= max_depth:
                print(f"Max depth reached at {folder_path}")
                return []
            
            print(f"Scanning folder: {folder_path} (depth: {current_depth})")
            
            if folder_path == "/":
                endpoint = '/me/drive/root/children'
            else:
                folder_path_clean = folder_path.lstrip('/')
                endpoint = f"/me/drive/root:/{folder_path_clean}:/children"
            
            items_data = self.make_graph_api_call(endpoint)
            if not items_data:
                return []
            
            items = items_data.get('value', [])
            files = []
            
            for item in items:
                item_name = item.get('name', 'Unknown')
                item_type = 'folder' if 'folder' in item else 'file'
                
                if item_type == 'file':
                    file_ext = item_name.lower().split('.')[-1] if '.' in item_name else 'unknown'
                    file_data = {
                        'name': item_name,
                        'id': item.get('id'),
                        'type': file_ext,
                        'size': item.get('size', 0),
                        'last_modified': item.get('lastModifiedDateTime'),
                        'path': folder_path,
                        'web_url': item.get('webUrl')
                    }
                    files.append(file_data)
                    print(f"Found file: {item_name}")
                elif item_type == 'folder':
                    # Recursively get files from subfolder
                    subfolder_path = f"{folder_path.rstrip('/')}/{item_name}" if folder_path != "/" else f"/{item_name}"
                    subfolder_files = self.get_files_recursively(subfolder_path, max_depth, current_depth + 1)
                    files.extend(subfolder_files)
            
            return files
            
        except Exception as e:
            print(f"Error scanning folder {folder_path}: {e}")
            return []

    def get_folder_files(self, folder_id):
        """Get all files from a specific folder"""
        try:
            endpoint = f"/me/drive/items/{folder_id}/children"
            items_data = self.make_graph_api_call(endpoint)
            
            if not items_data:
                return []
            
            files = []
            for item in items_data.get('value', []):
                if 'folder' not in item:
                    item_name = item.get('name', 'Unknown')
                    file_ext = item_name.lower().split('.')[-1] if '.' in item_name else 'unknown'
                    
                    file_data = {
                        'name': item_name,
                        'id': item.get('id'),
                        'type': file_ext,
                        'size': item.get('size', 0),
                        'last_modified': item.get('lastModifiedDateTime'),
                        'path': item.get('parentReference', {}).get('path', '/')
                    }
                    files.append(file_data)
            
            return files
            
        except Exception as e:
            print(f"Error getting folder files: {e}")
            return []

    def download_file_content(self, file_id, file_name, file_type):
        """Download file content with caching"""
        try:
            # Check cache first
            cache_key = f"{file_id}_{file_name}"
            if cache_key in self.file_cache:
                print(f"Using cached content for: {file_name}")
                return self.file_cache[cache_key]
            
            print(f"Downloading: {file_name}")
            
            headers = {'Authorization': f'Bearer {self.access_token}'}
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content"
            
            # Use streaming for large files
            response = requests.get(url, headers=headers, stream=True)
            if response.status_code == 200:
                # Read content in chunks for memory efficiency
                content_bytes = b''
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        content_bytes += chunk
                
                processed_content = self.read_file_content(content_bytes, file_name, file_type)
                
                # Cache the processed content
                self._add_to_cache(cache_key, processed_content)
                
                print(f"Downloaded and cached: {file_name}")
                return processed_content
            else:
                error_msg = f"Download failed: {response.status_code}"
                print(f"{error_msg}")
                return error_msg
                
        except Exception as e:
            error_msg = f"Download error: {str(e)}"
            print(f"{error_msg}")
            return error_msg
    
    def _add_to_cache(self, cache_key, content):
        """Add content to cache with LRU eviction"""
        # Remove oldest entries if cache is full
        if len(self.file_cache) >= self.cache_max_size:
            # Remove the first (oldest) entry
            oldest_key = next(iter(self.file_cache))
            del self.file_cache[oldest_key]
            print(f"Removed from cache: {oldest_key}")
        
        self.file_cache[cache_key] = content
        print(f"Cached: {cache_key}")
    
    def clear_cache(self):
        """Clear the file cache"""
        self.file_cache.clear()
        print("File cache cleared")

    def read_file_content(self, content, file_name, file_type):
        """Read file content based on type"""
        try:
            if file_type == 'txt':
                text_content = content.decode('utf-8', errors='ignore')[:10000]
                return f"Text file: {file_name}\nContent:\n{text_content}"
                
            elif file_type == 'pdf':
                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as f:
                    f.write(content)
                    f.flush()
                    pdf_reader = PyPDF2.PdfReader(f.name)
                    text = ""
                    for i, page in enumerate(pdf_reader.pages[:5]):
                        page_text = page.extract_text()
                        if page_text:
                            text += f"Page {i+1}:\n{page_text}\n\n"
                    os.unlink(f.name)
                    return f"PDF file: {file_name}\nExtracted text:\n{text}"
                    
            elif file_type in ['docx', 'doc']:
                doc = Document(io.BytesIO(content))
                text = "\n".join([p.text for p in doc.paragraphs[:50] if p.text.strip()])
                return f"Word document: {file_name}\nContent:\n{text}"
                
            elif file_type == 'csv':
                df = pd.read_csv(io.BytesIO(content), nrows=20)
                sample_data = df.head(3).to_string()
                return f"CSV file: {file_name}\nRows: {len(df)}, Columns: {len(df.columns)}\nSample data:\n{sample_data}"
                
            elif file_type in ['xlsx', 'xls']:
                df = pd.read_excel(io.BytesIO(content), nrows=20)
                sample_data = df.head(3).to_string()
                return f"Excel file: {file_name}\nRows: {len(df)}, Columns: {len(df.columns)}\nSample data:\n{sample_data}"
                
            else:
                return f"File: {file_name} (Type: {file_type})"
                
        except Exception as e:
            return f"Error reading {file_name}: {str(e)}"

    def query_selected_items(self, question, selected_items):
        """Query specific selected files/folders"""
        try:
            if not self.genai:
                return "Gemini AI is not available. Please check your API key."
            
            print(f"🤖 Processing question for {len(selected_items)} selected items: {question}")
            
            # Process all selected items
            all_contents = []
            total_items = len(selected_items)
            
            for i, item in enumerate(selected_items, 1):
                print(f"Processing item {i}/{total_items}: {item['name']} (type: {item['type']})")
                
                if item['type'] == 'file':
                    content = self.download_file_content(item['id'], item['name'], item.get('extension', 'unknown'))
                    if content and not content.startswith("Error"):
                        all_contents.append({
                            'name': item['name'],
                            'type': 'file',
                            'content': content[:3000]
                        })
                        print(f"Processed file: {item['name']}")
                    else:
                        print(f"ould not process file: {item['name']}")
                        
                elif item['type'] == 'folder':
                    # Get all files from the folder recursively
                    print(f"Processing folder: {item['name']}")
                    folder_files = self.get_folder_files(item['id'])
                    folder_contents = []
                    
                    # Process up to 5 files from the folder
                    for j, file_data in enumerate(folder_files[:5], 1):
                        print(f"Processing folder file {j}/5: {file_data['name']}")
                        content = self.download_file_content(file_data['id'], file_data['name'], file_data['type'])
                        if content and not content.startswith("Error"):
                            folder_contents.append({
                                'name': file_data['name'],
                                'content': content[:1500]
                            })
                            print(f"Processed folder file: {file_data['name']}")
                        else:
                            print(f"Could not process folder file: {file_data['name']}")
                    
                    if folder_contents:
                        all_contents.append({
                            'name': f"Folder: {item['name']}",
                            'type': 'folder',
                            'content': f"Contains {len(folder_files)} files. Sample files:\n" + 
                                      "\n".join([f"- {fc['name']}: {fc['content']}" for fc in folder_contents])
                        })
                        print(f"Processed folder: {item['name']} ({len(folder_files)} files, {len(folder_contents)} processed)")
                    else:
                        print(f"No content could be read from folder: {item['name']}")
            
            if not all_contents:
                return "❌ No content could be read from the selected items. Please check if the files are accessible and try again."
            
            print(f"Successfully processed {len(all_contents)} items for AI analysis")
            
            # Create context for Gemini
            context = "Selected Items Content:\n\n"
            for item_info in all_contents:
                context += f"--- {item_info['name']} ---\n{item_info['content']}\n\n"
            
            prompt = f"""Based on these selected files/folders:

{context}

Question: {question}

Please provide a helpful answer focusing specifically on the selected content. If multiple items are selected, analyze them together and provide insights about their relationships or differences."""

            print("Sending to Gemini...")
            response = self.genai.generate_content(prompt)
            print("Got Gemini response")
            
            return response.text
            
        except Exception as e:
            print(f"Error processing query: {e}")
            return f"Error processing query: {str(e)}"

    def query_files(self, question):
        """Query all files (fallback method)"""
        try:
            files = self.get_all_files_flat()[:5]  # Limit to 5 files
            if not files:
                return "No files found in your OneDrive."
            
            # Process files for Gemini
            file_contents = []
            for file_data in files:
                content = self.download_file_content(file_data['id'], file_data['name'], file_data['type'])
                if content and not content.startswith("Error"):
                    file_contents.append({
                        'name': file_data['name'],
                        'content': content[:3000]
                    })
            
            if not file_contents:
                return "Files were found but couldn't be read."
            
            context = "OneDrive Files:\n\n"
            for file_info in file_contents:
                context += f"--- {file_info['name']} ---\n{file_info['content']}\n\n"
            
            prompt = f"""Based on these OneDrive files:

{context}

Question: {question}

Please provide a helpful answer:"""
            
            response = self.genai.generate_content(prompt)
            return response.text
            
        except Exception as e:
            return f"Error: {str(e)}"

    def query_all_files(self, question):
        """Query ALL files in OneDrive when no specific files are selected"""
        try:
            if not self.genai:
                return "Gemini AI is not available. Please check your API key."
            
            print(f"🤖 Processing question with ALL OneDrive files: {question}")
            
            # Get all files from OneDrive
            files = self.get_all_files_flat()[:10]  # Limit to 10 files for performance
            if not files:
                # If no files found, provide a helpful response instead of error
                print("No files found in OneDrive, providing general response")
                return self.query_general_question(question)
            
            print(f"Found {len(files)} files to process")
            
            # Process files for Gemini
            file_contents = []
            for i, file_data in enumerate(files):
                print(f"Processing file {i+1}/{len(files)}: {file_data['name']}")
                content = self.download_file_content(file_data['id'], file_data['name'], file_data['type'])
                if content and not content.startswith("Error"):
                    file_contents.append({
                        'name': file_data['name'],
                        'type': file_data['type'],
                        'content': content[:2000]  # Limit content size
                    })
                    print(f"Successfully processed: {file_data['name']}")
                else:
                    print(f"Could not process: {file_data['name']}")
            
            if not file_contents:
                # If files found but couldn't be read, provide general response
                print("Files found but couldn't be read, providing general response")
                return self.query_general_question(question)
            
            print(f"📊 Successfully processed {len(file_contents)} files for AI analysis")
            
            # Create context for Gemini
            context = "All OneDrive Files Content:\n\n"
            for file_info in file_contents:
                context += f"--- {file_info['name']} ({file_info['type']}) ---\n{file_info['content']}\n\n"
            
            prompt = f"""Based on ALL the files in your OneDrive:

{context}

Question: {question}

Please provide a comprehensive answer based on the content of all your OneDrive files. If the question is about specific information, search through all the files to find relevant details."""

            response = self.genai.generate_content(prompt)
            return response.text
            
        except Exception as e:
            print(f"Error processing all files: {e}")
            # Fallback to general question if there's an error
            return self.query_general_question(question)

    def query_general_question(self, question):
        """Answer general questions without file context"""
        try:
            if not self.genai:
                return "Gemini AI is not available. Please check your API key."
            
            print(f"🤖 Processing general question: {question}")
            
            prompt = f"""You are a helpful AI assistant. The user is asking a question, but either no files are available in their OneDrive or there was an issue accessing them. 

Question: {question}

Please provide a helpful and informative answer. If the question seems to be about file management, OneDrive, or document analysis, you can provide general guidance on these topics. If it's a completely unrelated question, answer it as a helpful AI assistant would.

Note: - If the user is asking about their files specifically, let them know that you couldn't access their OneDrive files at the moment, but you can still help with general questions about file management, document analysis, or any other topics.
      - Give Response in proper format.  
      - Do not hallucinate
      - Make important points
      """
      
            response = self.genai.generate_content(prompt)
            return response.text
            
        except Exception as e:
            return f" Error processing general question: {str(e)}"

# Store assistants in memory
assistant_store = {}

def get_user_key():
    return session.get('email') or session.get('user', 'unknown')

# Template filter for rendering directory structure
@app.template_global()
def render_directory(structure, level=0):
    """Recursively render directory structure in templates"""
    html = ""
    for item in structure:
        # Determine icon based on file type
        if item['type'] == 'folder':
            icon = 'folder'
        else:
            file_ext = item.get('extension', '')
            if file_ext in ['pdf']:
                icon = 'file-pdf'
            elif file_ext in ['docx', 'doc']:
                icon = 'file-word'
            elif file_ext in ['xlsx', 'xls']:
                icon = 'file-excel'
            elif file_ext in ['csv']:
                icon = 'file-csv'
            elif file_ext in ['txt']:
                icon = 'file-alt'
            elif file_ext in ['pptx', 'ppt']:
                icon = 'file-powerpoint'
            else:
                icon = 'file'
        
        html += f'''
        <div class="file-item" 
             id="{item['id']}" 
             data-name="{item['name']}" 
             data-type="{item['type']}"
             data-extension="{item.get('extension', '')}">
            <div class="file-checkbox">
                <input type="checkbox">
                <span class="checkmark"></span>
            </div>
            <i class="fas fa-{icon} file-{item.get('extension', 'default')}"></i>
            <span class="file-name">{item['name']}</span>
            {f'<span class="file-type">{item.get("extension", "").upper()}</span>' if item['type'] == 'file' else ''}
        </div>
        '''
        
        # Recursively render children for folders
        if item['type'] == 'folder' and item.get('children'):
            html += f'<div class="folder-contents">'
            html += render_directory(item['children'], level + 1)
            html += '</div>'
    
    return html

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')

@app.route('/login')
def login():
    msal_app = ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
    auth_url = msal_app.get_authorization_request_url(SCOPES, redirect_uri=REDIRECT_URI)
    return redirect(auth_url)

@app.route('/auth/callback')
def auth_callback():
    try:
        code = request.args.get('code')
        if not code:
            return "No authorization code received"
        
        msal_app = ConfidentialClientApplication(CLIENT_ID, authority=AUTHORITY, client_credential=CLIENT_SECRET)
        result = msal_app.acquire_token_by_authorization_code(code, scopes=SCOPES, redirect_uri=REDIRECT_URI)
        
        if 'access_token' in result:
            headers = {'Authorization': f'Bearer {result["access_token"]}'}
            user_data = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers).json()
            
            session['user'] = user_data.get('displayName', 'User')
            session['access_token'] = result['access_token']
            session['email'] = user_data.get('mail', '')
            
            print(f" User authenticated: {session['user']}")
            
            # Initialize assistant
            assistant = OneDriveGeminiAssistant(result["access_token"])
            user_key = get_user_key()
            assistant_store[user_key] = assistant
            
            return redirect(url_for('chat'))
        else:
            return f"Authentication failed: {result.get('error_description', 'Unknown error')}"
            
    except Exception as e:
        return f"Authentication error: {str(e)}"

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('index'))
    
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    # Get directory structure for the file browser
    directory_structure = []
    if assistant:
        directory_structure = assistant.get_directory_structure()
    
    return render_template('chat.html', 
                         username=session['user'],
                         directory_structure=directory_structure)

@app.route('/api/chat', methods=['POST','GET'])
def api_chat():
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    if not assistant:
        return jsonify({'error': 'Not authenticated'})
    
    data = request.json
    question = data.get('question', '')
    selected_items = data.get('selected_items', [])
    
    if not question:
        return jsonify({'error': 'No question provided'})
    
    try:
        # If specific items are selected, query only those
        if selected_items and len(selected_items) > 0:
            response = assistant.query_selected_items(question, selected_items)
        else:
            # When no files are selected, access ALL files in OneDrive
            response = assistant.query_all_files(question)
            
        return jsonify({
            'response': response,
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/directory')
def api_directory():
    """API endpoint to get directory structure"""
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    if not assistant:
        return jsonify({'error': 'Not authenticated'})
    
    try:
        directory_structure = assistant.get_directory_structure()
        return jsonify({
            'success': True,
            'directory': directory_structure
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/debug')
def debug():
    if 'user' not in session:
        return "Not authenticated"
    
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    if not assistant:
        return "No assistant"
    
    debug_info = assistant.test_connection()
    
    # Add Gemini debug info
    gemini_status = " Not available"
    if assistant.genai:
        gemini_status = " Available"
    
    debug_info += f"\n\n=== GEMINI AI STATUS ===\n"
    debug_info += f"API Key Present: {'Yes' if GEMINI_API_KEY else ' No'}\n"
    debug_info += f"API Key Length: {len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}\n"
    debug_info += f"Gemini Model: {gemini_status}\n"
    
    # Add file access debug info
    debug_info += f"\n\n=== FILE ACCESS DEBUG ===\n"
    try:
        files = assistant.get_all_files_flat()
        debug_info += f"Files found: {len(files)}\n"
        if files:
            debug_info += f"Sample files:\n"
            for i, file in enumerate(files[:3]):
                debug_info += f"  {i+1}. {file['name']} ({file['type']})\n"
        else:
            debug_info += "No files found - this might be why Gemini says 'No files found'\n"
    except Exception as e:
        debug_info += f"Error getting files: {e}\n"
    
    return f"<pre>{debug_info}</pre>"

@app.route('/test-gemini')
def test_gemini():
    """Test Gemini API directly"""
    try:
        if not GEMINI_API_KEY:
            return jsonify({'error': 'No Gemini API key found'})
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content("Hello, this is a test. Please respond with 'Gemini is working!'")
        
        return jsonify({
            'success': True,
            'response': response.text,
            'model': 'gemini-2.5-flash'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'api_key_present': bool(GEMINI_API_KEY),
            'api_key_length': len(GEMINI_API_KEY) if GEMINI_API_KEY else 0
        })

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear file cache"""
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    if not assistant:
        return jsonify({'error': 'Not authenticated'})
    
    try:
        assistant.clear_cache()
        return jsonify({
            'success': True,
            'message': 'File cache cleared successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/cache/status')
def cache_status():
    """Get cache status"""
    user_key = get_user_key()
    assistant = assistant_store.get(user_key)
    
    if not assistant:
        return jsonify({'error': 'Not authenticated'})
    
    try:
        cache_size = len(assistant.file_cache)
        cache_max = assistant.cache_max_size
        cache_keys = list(assistant.file_cache.keys())
        
        return jsonify({
            'success': True,
            'cache_size': cache_size,
            'cache_max': cache_max,
            'cache_usage_percent': round((cache_size / cache_max) * 100, 2),
            'cached_files': cache_keys[:10]  # Show first 10 cached files
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/logout')
def logout():
    user_key = get_user_key()
    if user_key in assistant_store:
        del assistant_store[user_key]
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    print(" Starting OneDrive + Gemini Flask App...")
    print(" Now with file/folder selection!")
    port = int(os.getenv('PORT', 5000))  
    app.run(debug=False, host='0.0.0.0', port=port)
