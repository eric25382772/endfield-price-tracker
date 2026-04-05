document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const previewArea = document.getElementById('previewArea');
    const preview = document.getElementById('preview');
    const form = document.getElementById('uploadForm');

    // Store pasted file so we can submit it
    let pastedFile = null;

    // Ctrl+V paste from clipboard (listen on whole page)
    document.addEventListener('paste', function(e) {
        const items = e.clipboardData && e.clipboardData.items;
        if (!items) return;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                e.preventDefault();
                const blob = items[i].getAsFile();
                // Convert to a proper File with a filename
                pastedFile = new File([blob], 'clipboard_screenshot.png', { type: blob.type });

                // Assign to file input via DataTransfer
                const dt = new DataTransfer();
                dt.items.add(pastedFile);
                fileInput.files = dt.files;

                showPreview(pastedFile);
                dropZone.querySelector('p').textContent = '✓ 已貼上剪貼簿截圖';
                return;
            }
        }
    });

    // Drag and drop
    if (dropZone) {
        ['dragenter', 'dragover'].forEach(evt => {
            dropZone.addEventListener(evt, e => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(evt => {
            dropZone.addEventListener(evt, e => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            });
        });

        dropZone.addEventListener('drop', e => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                fileInput.files = files;
                pastedFile = null;
                showPreview(files[0]);
            }
        });
    }

    // File input change preview
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (this.files.length > 0) {
                pastedFile = null;
                showPreview(this.files[0]);
            }
        });
    }

    function showPreview(file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            preview.src = e.target.result;
            previewArea.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }

    // Validate and show loading on submit
    if (form) {
        form.addEventListener('submit', function(e) {
            const hasFile = fileInput.files && fileInput.files.length > 0;
            if (!hasFile) {
                e.preventDefault();
                alert('請先貼上截圖 (Ctrl+V) 或選擇檔案');
                return;
            }

            const btn = document.getElementById('submitBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>辨識中...';
        });
    }
});
