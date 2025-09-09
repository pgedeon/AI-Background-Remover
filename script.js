document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('file-input');
    const gallery = document.getElementById('gallery');
    const selectAllButton = document.getElementById('select-all');
    const downloadSelectedButton = document.getElementById('download-selected');
    const processButton = document.getElementById('process-images');
    const objectTypeSelect = document.getElementById('object-type');
    const presetSelect = document.getElementById('preset');
    const trimapThresholdInput = document.getElementById('trimap-threshold');
    const trimapThresholdValue = document.getElementById('trimap-threshold-value');
    const trimapDilationInput = document.getElementById('trimap-dilation');
    const trimapDilationValue = document.getElementById('trimap-dilation-value');
    const trimapErosionInput = document.getElementById('trimap-erosion');
    const trimapErosionValue = document.getElementById('trimap-erosion-value');
    const featherRadiusInput = document.getElementById('feather-radius');
    const featherRadiusValue = document.getElementById('feather-radius-value');
    const alphaThresholdInput = document.getElementById('alpha-threshold');
    const alphaThresholdValue = document.getElementById('alpha-threshold-value');
    const runtimeInfo = document.getElementById('runtime-info');

    let uploadedFiles = [];

    // Initialize range input displays
    trimapThresholdValue.textContent = trimapThresholdInput.value;
    trimapDilationValue.textContent = trimapDilationInput.value;
    trimapErosionValue.textContent = trimapErosionInput.value;
    featherRadiusValue.textContent = featherRadiusInput.value;
    alphaThresholdValue.textContent = alphaThresholdInput.value;

    // Add event listeners for range inputs
    trimapThresholdInput.addEventListener('input', () => {
        trimapThresholdValue.textContent = trimapThresholdInput.value;
    });

    trimapDilationInput.addEventListener('input', () => {
        trimapDilationValue.textContent = trimapDilationInput.value;
    });

    trimapErosionInput.addEventListener('input', () => {
        trimapErosionValue.textContent = trimapErosionInput.value;
        maybeSetCustomPreset();
    });
    featherRadiusInput.addEventListener('input', () => {
        featherRadiusValue.textContent = featherRadiusInput.value;
        maybeSetCustomPreset();
    });
    alphaThresholdInput.addEventListener('input', () => {
        alphaThresholdValue.textContent = alphaThresholdInput.value;
        maybeSetCustomPreset();
    });
    objectTypeSelect.addEventListener('change', () => {
        maybeSetCustomPreset();
    });

    // Presets mapping
    const presets = {
        auto: { object_type: 'hairs-like', trimap_prob_threshold: 231, trimap_dilation: 30, trimap_erosion_iters: 5, feather_radius: 0, alpha_threshold: 0 },
        portrait: { object_type: 'hairs-like', trimap_prob_threshold: 230, trimap_dilation: 24, trimap_erosion_iters: 4, feather_radius: 1.5, alpha_threshold: 0 },
        product: { object_type: 'object', trimap_prob_threshold: 240, trimap_dilation: 18, trimap_erosion_iters: 3, feather_radius: 0.5, alpha_threshold: 10 },
        illustration: { object_type: 'object', trimap_prob_threshold: 245, trimap_dilation: 14, trimap_erosion_iters: 2, feather_radius: 0, alpha_threshold: 0 },
    };

    presetSelect.addEventListener('change', () => {
        const p = presets[presetSelect.value];
        if (!p) return; // custom
        objectTypeSelect.value = p.object_type;
        trimapThresholdInput.value = String(p.trimap_prob_threshold);
        trimapDilationInput.value = String(p.trimap_dilation);
        trimapErosionInput.value = String(p.trimap_erosion_iters);
        featherRadiusInput.value = String(p.feather_radius);
        alphaThresholdInput.value = String(p.alpha_threshold);
        // Update labels
        trimapThresholdValue.textContent = trimapThresholdInput.value;
        trimapDilationValue.textContent = trimapDilationInput.value;
        trimapErosionValue.textContent = trimapErosionInput.value;
        featherRadiusValue.textContent = featherRadiusInput.value;
        alphaThresholdValue.textContent = alphaThresholdInput.value;
    });

    function maybeSetCustomPreset() {
        if (presetSelect.value !== 'custom') presetSelect.value = 'custom';
    }

    // Drag & drop support
    ;['dragenter','dragover'].forEach(evt =>
        gallery.addEventListener(evt, e => {
            e.preventDefault();
            e.stopPropagation();
            gallery.classList.add('dragging');
        })
    );
    ;['dragleave','drop'].forEach(evt =>
        gallery.addEventListener(evt, e => {
            e.preventDefault();
            e.stopPropagation();
            if (evt === 'dragleave') gallery.classList.remove('dragging');
        })
    );
    gallery.addEventListener('drop', e => {
        gallery.classList.remove('dragging');
        const files = Array.from(e.dataTransfer.files || []).filter(f => f.type.startsWith('image/'));
        if (files.length) {
            uploadedFiles = files;
            displayImages(files);
        }
    });

    fileInput.addEventListener('change', (event) => {
        const files = Array.from(event.target.files);
        uploadedFiles = files;
        displayImages(files);
    });

    function displayImages(files) {
        gallery.innerHTML = '';
        files.forEach((file, index) => {
            const reader = new FileReader();
            reader.onload = (e) => {
                const wrapper = document.createElement('div');
                wrapper.className = 'thumb';
                const img = document.createElement('img');
                img.src = e.target.result;
                img.dataset.index = index;
                img.addEventListener('click', () => {
                    img.classList.toggle('selected');
                });
                const caption = document.createElement('div');
                caption.className = 'caption';
                caption.textContent = file.name;
                wrapper.appendChild(img);
                wrapper.appendChild(caption);
                gallery.appendChild(wrapper);
            };
            reader.readAsDataURL(file);
        });
    }

    selectAllButton.addEventListener('click', () => {
        const images = gallery.querySelectorAll('img');
        const allSelected = Array.from(images).every(img => img.classList.contains('selected'));
        images.forEach(img => {
            if (allSelected) {
                img.classList.remove('selected');
            } else {
                img.classList.add('selected');
            }
        });
    });

    processButton.addEventListener('click', async () => {
        const selectedImages = gallery.querySelectorAll('img.selected');
        if (selectedImages.length === 0) {
            alert('Please select images to process.');
            return;
        }

        setLoading(true);
        const formData = new FormData();
        const selectedIndexes = Array.from(selectedImages).map(img => parseInt(img.dataset.index));

        selectedIndexes.forEach(index => {
            formData.append('images', uploadedFiles[index]);
        });

        // Build query string with carvekit settings
        const params = new URLSearchParams();
        params.append('object_type', objectTypeSelect.value);
        params.append('trimap_prob_threshold', trimapThresholdInput.value);
        params.append('trimap_dilation', trimapDilationInput.value);
        params.append('trimap_erosion_iters', trimapErosionInput.value);
        params.append('feather_radius', featherRadiusInput.value);
        params.append('alpha_threshold', alphaThresholdInput.value);

        try {
            const response = await fetch(`/upload?${params.toString()}`, {
                method: 'POST',
                body: formData
            });

            const payload = await response.json().catch(() => null);
            if (!response.ok || !payload) {
                throw new Error('Image processing failed');
            }

            // payload.results = [{ok, url, name, error, ms}]
            displayProcessedResults(payload.results || []);
        } catch (error) {
            console.error('Error:', error);
            alert('An error occurred while processing the images.');
        } finally {
            setLoading(false);
        }
    });

    function displayProcessedResults(results) {
        gallery.innerHTML = '';
        results.forEach(item => {
            const wrapper = document.createElement('div');
            wrapper.className = 'thumb';
            const img = document.createElement('img');

            if (item.ok) {
                img.src = item.url;
                img.classList.add('processed');
            } else {
                img.alt = 'Error';
                img.classList.add('error');
                const placeholder = 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(
                    `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200">
                        <rect width="100%" height="100%" fill="#ffe6e6"/>
                        <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#cc0000" font-family="sans-serif" font-size="14">
                            ${escapeHtml(item.error || 'Failed')}
                        </text>
                    </svg>`
                );
                img.src = placeholder;
            }

            const caption = document.createElement('div');
            caption.className = 'caption';
            caption.textContent = item.ok ? `${item.name} ✓ (${item.ms || 0}ms)` : `${item.name} ✗`;

            wrapper.appendChild(img);
            wrapper.appendChild(caption);
            gallery.appendChild(wrapper);
        });
    }

    function setLoading(loading) {
        processButton.disabled = loading;
        selectAllButton.disabled = loading;
        downloadSelectedButton.disabled = loading;
        processButton.textContent = loading ? 'Processing…' : 'Process Images';
    }

    function escapeHtml(str) {
        return String(str).replace(/[&<>"']/g, function (s) {
            const map = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            };
            return map[s] || '';
        });
    }

    downloadSelectedButton.addEventListener('click', () => {
        const processedImages = gallery.querySelectorAll('img.processed');
        if (processedImages.length === 0) {
            alert('No processed images to download.');
            return;
        }
        processedImages.forEach(img => {
            const link = document.createElement('a');
            link.href = img.src;
            link.download = (img.src.split('/').pop() || 'image.png').split('?')[0];
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    });

    // Fetch and display runtime info
    (async function loadInfo(){
        try {
            const r = await fetch('/info', { cache: 'no-store' });
            if (!r.ok) throw new Error('info not ok');
            const j = await r.json();
            runtimeInfo.textContent = `Device: ${j.device}${j.gpu ? ' ('+j.gpu+')' : ''} · Torch ${j.torch} · FP16: ${j.fp16 ? 'on' : 'off'} · PNG level: ${j.png_compress_level}`;
        } catch (e) {
            runtimeInfo.textContent = 'Backend info unavailable';
        }
    })();
});
