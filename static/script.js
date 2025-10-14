class ChatApp {
    constructor() {
        this.selectedFiles = [];
        this.viewMode = 'list';
        this.initializeEventListeners();
        this.updateCurrentTime();
        this.initializeFileSelection();
    }

    initializeEventListeners() {
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const suggestions = document.querySelectorAll('.suggestion');

        // Send message on button click
        sendButton.addEventListener('click', () => this.sendMessage());

        // Send message on Enter key
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Enable/disable send button based on input
        messageInput.addEventListener('input', () => {
            sendButton.disabled = messageInput.value.trim() === '';
        });

        // Suggestion clicks
        suggestions.forEach(suggestion => {
            suggestion.addEventListener('click', () => {
                const question = suggestion.getAttribute('data-question');
                messageInput.value = question;
                this.sendMessage();
            });
        });

        // Auto-focus input
        messageInput.focus();
    }

    initializeFileSelection() {
        console.log('File selection initialized');
        
        // Add event delegation for file item clicks and checkbox changes
        document.addEventListener('click', (e) => {
            // Handle checkbox clicks
            if (e.target.type === 'checkbox' && e.target.closest('.file-item')) {
                e.stopPropagation(); // Prevent file item click
                const fileItem = e.target.closest('.file-item');
                const fileId = fileItem.id;
                const fileName = fileItem.dataset.name;
                const fileType = fileItem.dataset.type;
                const fileExtension = fileItem.dataset.extension;
                
                console.log('Checkbox clicked for:', fileName);
                this.toggleFileSelection(fileId, fileName, fileType, fileExtension);
            }
            // Handle file item clicks (but not checkbox clicks)
            else if (e.target.closest('.file-item') && e.target.type !== 'checkbox') {
                const fileItem = e.target.closest('.file-item');
                const fileId = fileItem.id;
                const fileName = fileItem.dataset.name;
                const fileType = fileItem.dataset.type;
                const fileExtension = fileItem.dataset.extension;
                
                console.log('File item clicked:', fileName);
                this.toggleFileSelection(fileId, fileName, fileType, fileExtension);
            }
        });
    }

    toggleFileSelection(fileId, fileName, fileType, fileExtension) {
        console.log('Toggle selection called for:', fileName);
        
        // Find if file is already selected
        const existingIndex = this.selectedFiles.findIndex(f => f.id === fileId);
        
        if (existingIndex > -1) {
            // Remove from selection
            this.selectedFiles.splice(existingIndex, 1);
            console.log(`❌ Removed ${fileName} from selection`);
        } else {
            // Add to selection
            this.selectedFiles.push({
                id: fileId,
                name: fileName,
                type: fileType,
                extension: fileExtension
            });
            console.log(`✅ Added ${fileName} to selection`);
        }
        
        console.log(`Total selected: ${this.selectedFiles.length}`);
        this.updateSelectionUI();
    }

    selectFile(fileId, fileName, fileType, fileExtension) {
        // Add file to selection if not already selected
        const existingIndex = this.selectedFiles.findIndex(f => f.id === fileId);
        if (existingIndex === -1) {
            this.selectedFiles.push({
                id: fileId,
                name: fileName,
                type: fileType,
                extension: fileExtension
            });
        }
        
        this.updateSelectionUI();
    }

    unselectFile(fileId) {
        console.log('Unselect file called for ID:', fileId);
        
        // Remove from selection array
        const index = this.selectedFiles.findIndex(f => f.id === fileId);
        if (index > -1) {
            this.selectedFiles.splice(index, 1);
        }
        
        // Find and uncheck the checkbox
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            const fileItem = checkbox.closest('.file-item');
            if (fileItem && fileItem.id === fileId) {
                checkbox.checked = false;
                fileItem.classList.remove('selected');
            }
        });
        
        this.updateSelectionUI();
        console.log(`Total selected now: ${this.selectedFiles.length}`);
    }

    updateSelectionUI() {
        // Update selected count
        const selectedCount = document.getElementById('selectedCount');
        if (selectedCount) {
            selectedCount.textContent = 
                `${this.selectedFiles.length} file${this.selectedFiles.length !== 1 ? 's' : ''} selected`;
        }
        
        // Update selection mode indicator
        const selectionMode = document.getElementById('selectionMode');
        if (selectionMode) {
            if (this.selectedFiles.length === 0) {
                selectionMode.innerHTML = '<i class="fas fa-globe"></i><span>Searching ALL files</span>';
                selectionMode.className = 'selection-mode';
            } else {
                selectionMode.innerHTML = '<i class="fas fa-check-circle"></i><span>Searching selected files only</span>';
                selectionMode.className = 'selection-mode searching-selected';
            }
        }
        
        // Update selected items display
        const selectedItems = document.getElementById('selectedItems');
        if (selectedItems) {
            if (this.selectedFiles.length === 0) {
                selectedItems.innerHTML = '<div class="no-selection">No files selected - will search all files</div>';
            } else {
                selectedItems.innerHTML = this.selectedFiles.map(file => `
                    <div class="selected-item">
                        <i class="fas fa-${this.getFileIcon(file.extension)}"></i>
                        <span>${file.name}</span>
                        <button class="unselect-btn" onclick="unselectFile('${file.id}')" title="Remove from selection">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                `).join('');
            }
        }
        
        // Update file item visual states and checkboxes
        document.querySelectorAll('.file-item').forEach(item => {
            const isSelected = this.selectedFiles.some(f => f.id === item.id);
            
            // Update visual state
            item.classList.toggle('selected', isSelected);
            
            // Update checkbox state
            const checkbox = item.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = isSelected;
                console.log(`Updated checkbox for ${item.dataset.name}: ${isSelected}`);
            }
        });
        
        // Debug logging
        console.log('Selection updated:', {
            selectedCount: this.selectedFiles.length,
            selectedFiles: this.selectedFiles.map(f => f.name)
        });
    }

    getFileIcon(extension) {
        const iconMap = {
            'pdf': 'file-pdf',
            'docx': 'file-word',
            'doc': 'file-word',
            'xlsx': 'file-excel',
            'xls': 'file-excel',
            'csv': 'file-csv',
            'txt': 'file-alt',
            'pptx': 'file-powerpoint',
            'ppt': 'file-powerpoint',
            'jpg': 'file-image',
            'jpeg': 'file-image',
            'png': 'file-image',
            'gif': 'file-image'
        };
        return iconMap[extension] || 'file';
    }

    selectAllFiles() {
        console.log('Selecting all files...');
        
        // Clear current selection
        this.selectedFiles = [];
        
        // Get all file items and add them to selection
        const allFileItems = document.querySelectorAll('.file-item');
        allFileItems.forEach(item => {
            const fileId = item.id;
            const fileName = item.dataset.name;
            const fileType = item.dataset.type;
            const fileExtension = item.dataset.extension;
            
            this.selectedFiles.push({
                id: fileId,
                name: fileName,
                type: fileType,
                extension: fileExtension
            });
        });
        
        console.log(`Selected ${this.selectedFiles.length} files`);
        this.updateSelectionUI();
    }

    clearSelection() {
        console.log('Clearing all selections...');
        
        // Clear selection array
        this.selectedFiles = [];
        
        // Remove selected class from all file items
        const fileItems = document.querySelectorAll('.file-item');
        fileItems.forEach(item => {
            item.classList.remove('selected');
        });
        
        console.log('Cleared all selections');
        this.updateSelectionUI();
    }

    toggleViewMode() {
        this.viewMode = this.viewMode === 'list' ? 'grid' : 'list';
        // Implement view mode toggle
        console.log('View mode:', this.viewMode);
    }


    async sendMessage() {
        const messageInput = document.getElementById('messageInput');
        const message = messageInput.value.trim();

        if (!message) return;

        // Clear input and disable send button
        messageInput.value = '';
        document.getElementById('sendButton').disabled = true;

        // Add user message to chat
        this.addMessage(message, 'user');

        // Show typing indicator
        this.showTypingIndicator();

        try {
            // Prepare request data with selected files
            const requestData = {
                question: message,
                selected_items: this.selectedFiles
            };

            console.log('Sending message with selected files:', this.selectedFiles);

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            // Remove typing indicator
            this.hideTypingIndicator();

            if (data.error) {
                this.addMessage(`Error: ${data.error}`, 'bot');
            } else {
                this.addMessage(data.response, 'bot');
            }

        } catch (error) {
            this.hideTypingIndicator();
            this.addMessage('Sorry, there was an error processing your request.', 'bot');
            console.error('Error:', error);
        }
    }

    addMessage(text, sender) {
        const chatMessages = document.getElementById('chatMessages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;

        const avatarIcon = sender === 'bot' ? 'fas fa-robot' : 'fas fa-user';
        const time = this.getCurrentTime();

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="${avatarIcon}"></i>
            </div>
            <div class="message-content">
                <div class="message-text">${this.escapeHtml(text)}</div>
                <div class="message-time">${time}</div>
            </div>
        `;

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    showTypingIndicator() {
        const chatMessages = document.getElementById('chatMessages');
        const typingDiv = document.createElement('div');
        typingDiv.className = 'message bot-message';
        typingDiv.id = 'typingIndicator';

        typingDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="typing-indicator">
                <div class="typing-dots">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        `;

        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typingIndicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getCurrentTime() {
        return new Date().toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: true 
        });
    }

    updateCurrentTime() {
        const timeElement = document.getElementById('currentTime');
        if (timeElement) {
            timeElement.textContent = this.getCurrentTime();
        }
    }
}

// Global functions for HTML onclick handlers
function selectAllFiles() {
    if (window.chatApp) {
        window.chatApp.selectAllFiles();
    }
}

function clearSelection() {
    if (window.chatApp) {
        window.chatApp.clearSelection();
    }
}

function unselectFile(fileId) {
    console.log('Unselect file called for ID:', fileId);
    if (window.chatApp) {
        window.chatApp.unselectFile(fileId);
    }
}

function toggleFileSelection(fileId, fileName, fileType, fileExtension) {
    console.log('Global toggleFileSelection called:', { fileId, fileName, fileType, fileExtension });
    
    if (window.chatApp) {
        window.chatApp.toggleFileSelection(fileId, fileName, fileType, fileExtension);
    } else {
        console.error('chatApp not found!');
    }
}

function toggleViewMode() {
    if (window.chatApp) {
        window.chatApp.toggleViewMode();
    }
}

function reinitializeFiles() {
    // Reload the page to refresh files
    window.location.reload();
}

function clearCache() {
    if (confirm('Are you sure you want to clear the file cache? This will require re-downloading files.')) {
        fetch('/api/cache/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('✅ File cache cleared successfully!');
            } else {
                alert('❌ Error clearing cache: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('❌ Error clearing cache');
        });
    }
}

function getCacheStatus() {
    fetch('/api/cache/status')
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Cache Status:', {
                size: data.cache_size,
                max: data.cache_max,
                usage: data.cache_usage_percent + '%',
                files: data.cached_files
            });
            alert(`Cache Status:\nFiles cached: ${data.cache_size}/${data.cache_max}\nUsage: ${data.cache_usage_percent}%`);
        } else {
            console.error('Cache status error:', data.error);
        }
    })
    .catch(error => {
        console.error('Error getting cache status:', error);
    });
}

function testSelection() {
    if (window.chatApp) {
        console.log('=== SELECTION TEST ===');
        console.log('Current selection:', window.chatApp.selectedFiles);
        console.log('Selected files count:', window.chatApp.selectedFiles.length);
        
        const fileNames = window.chatApp.selectedFiles.map(f => f.name).join('\n') || 'No files selected';
        alert(`Selected ${window.chatApp.selectedFiles.length} files:\n${fileNames}`);
        
        // Test checkbox states
        const checkboxes = document.querySelectorAll('input[type="checkbox"]');
        console.log('Total checkboxes found:', checkboxes.length);
        let checkedCount = 0;
        checkboxes.forEach((checkbox, index) => {
            if (checkbox.checked) {
                checkedCount++;
                console.log(`Checkbox ${index} is checked`);
            }
        });
        console.log('Checked checkboxes:', checkedCount);
    }
}


// Initialize the chat app when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.chatApp = new ChatApp();
});